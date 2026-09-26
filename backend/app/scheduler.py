"""Планировщик: что платформа делает сама, по часам (пакет G, G3).

До него фоновых задач у платформы не было вовсе. Сверка неоплаты жила скриптом, запуск
которого был «решением эксплуатации», — и пока его никто не запускал, отток на сводке
навсегда оставался «не измеряется», а следа перехода в неоплату не оставалось.

**Механизм — Celery beat.** Celery и Redis в проекте уже есть; второй механизм фоновых
задач был бы второй правдой о том, что и когда запускается. Здесь — сама работа: чистые
по смыслу функции над базой, которые зовут и задача планировщика (``app.tasks``), и
скрипт эксплуатации (``scripts/*``). Две копии одной сверки однажды разошлись бы.

**Каждый суточный запуск оставляет след в служебном журнале — даже когда делать было
нечего** («просроченных нет»). По этим строкам экран готовности установки (G9) отвечает
«работает ли планировщик», а не гадает: молчание журнала значит «не запускался», а не
«всё хорошо».

Доступ этот модуль **не решает**: режим чтения при неоплате выводится из даты конца
периода на каждом запросе (``billing_period.effective_status``) и работает и без
планировщика. Планировщик приводит хранимое к выведенному и оставляет **след** — вывод
отвечает «как сейчас», а отток спрашивает «когда это произошло».
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crud, mail
from .billing import is_paid_plan
from .billing_period import (
    GRACE_DAYS,
    OVERDUE_STATUS,
    days_overdue,
    effective_status,
    reminder_stage,
)
from .database import as_tenant
from .db_models import AuditLogEntry, StaffLogEntry, Subscription, User
from .plans import PRODUCT_NAME, get_plan
from .rbac import Perm, has_permission
from .timefmt import when_utc

#: Задачи планировщика и их действие в служебном журнале. Перечень закрыт: экран
#: готовности читает ровно эти строки, и задача мимо перечня была бы невидимой.
TASKS: dict[str, str] = {
    "expire": "scheduler.expire",
    "reminders": "scheduler.reminders",
}


def record_run(db: Session, task: str, details: str) -> None:
    """След запуска в служебном журнале. Автора нет — это платформа, а не человек."""
    crud.log_staff_action(db, None, TASKS[task], details=details)


def last_runs(db: Session) -> dict[str, datetime | None]:
    """Когда каждая задача запускалась в последний раз. ``None`` — **ни разу**."""
    out: dict[str, datetime | None] = {}
    for task, action in TASKS.items():
        out[task] = db.execute(
            select(StaffLogEntry.created_at)
            .where(StaffLogEntry.action == action)
            .order_by(StaffLogEntry.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    return out


def overdue_subscriptions(db: Session, now: datetime) -> list[Subscription]:
    """Подписки, у которых выведенный статус разошёлся с хранимым.

    Отбор идёт по **выведенному** состоянию, а не по SQL-условию на дату: условие было
    бы второй копией правила, и разойтись с ``effective_status`` ему ничего не мешает.
    """
    rows = db.execute(select(Subscription)).scalars().all()
    return [s for s in rows
            if effective_status(s.status, s.current_period_end, now) != s.status]


#: Кто провёл запуск — слово для следа. Ручной запуск скрипта эксплуатации не должен
#: выглядеть работающим планировщиком: экран готовности спрашивает именно о нём.
SOURCE_SCHEDULER = "планировщик"
SOURCE_SCRIPT = "скрипт эксплуатации"


def expire_overdue(db: Session, now: datetime, *, dry_run: bool = False,
                   source: str = SOURCE_SCHEDULER) -> list[tuple[Subscription, int]]:
    """Перевести просроченные подписки в ``past_due`` и записать это в их журналы.

    Идемпотентна: повторный запуск в тот же день ничего не меняет и в журналы клиентов
    ничего не пишет. След самого запуска остаётся в служебном журнале всегда, кроме
    пробного прогона: «проверили — просроченных нет» тоже ответ.

    Возвращает пары «подписка — сколько суток просрочено» (для вывода скрипта).
    """
    changed: list[tuple[Subscription, int]] = []
    for sub in overdue_subscriptions(db, now):
        days = days_overdue(sub.current_period_end, now)
        changed.append((sub, days))
        if dry_run:
            continue
        sub.status = OVERDUE_STATUS
        db.commit()
        # Журнал под RLS, а запись идёт в чужую организацию: заходим в неё той же
        # дверью, что и все остальные (правило C3), и выходим обратно.
        with as_tenant(db, sub.organization_id):
            crud.log_action(
                db, sub.organization_id, None, "billing.overdue",
                entity_type="organization", entity_id=sub.organization_id,
                entity_name=sub.plan_code,
                details=f"{sub.product}: оплаченный период и льготный срок истекли "
                        f"({days} дн. с конца периода)")
    if not dry_run:
        record_run(db, "expire",
                   f"{source}: в неоплату переведено {len(changed)}" if changed
                   else f"{source}: просроченных подписок нет")
    return changed


# --- Письма о деньгах (G4) ---

#: Как этап письма назван в журнале организации: клиент читает «напоминание о конце
#: периода», а не «ending».
STAGE_LABEL = {
    "ending": "напоминание о конце оплаченного периода",
    "ended": "письмо об окончании периода",
    "overdue": "письмо о закрытии изменения данных",
}


@dataclass
class ReminderRun:
    """Итог рассылки — по подпискам, а не по письмам: одной подписке пишут всем, кто
    вправе платить, а вопрос экрана — «дошло ли до организации»."""

    sent: int = 0            # ушло хотя бы одному адресату
    failed: int = 0          # не ушло никому — причина в журнале организации
    mail_off: int = 0        # полагалось, но почта выключена: не пытались
    no_recipients: int = 0   # некому: владелец приостановлен или заблокирован


def _payers(db: Session, org_id: str) -> list[User]:
    """Кому писать о деньгах: тем, кто вправе платить, и только действующим.

    Приостановленный участник и заблокированная учётная запись письма не получают:
    отстранённому человеку платёжные новости организации больше не принадлежат.
    """
    return [user for membership, user in crud.list_members(db, org_id)
            if has_permission(membership.role, Perm.BILLING_MANAGE)
            and membership.blocked_at is None and user.blocked_at is None and user.email]


def _reminder_key(sub: Subscription, stage: str) -> str:
    """Ключ письма в журнале: продукт + конец **этого** периода + этап. Новый период —
    новый ключ, поэтому следующее продление снова получит свои письма."""
    end = sub.current_period_end
    assert end is not None
    aware = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    return f"{sub.product}:{aware.date().isoformat()}:{stage}"


def _already_sent(db: Session, org_id: str, key: str) -> bool:
    return db.execute(
        select(AuditLogEntry.id)
        .where(AuditLogEntry.organization_id == org_id,
               AuditLogEntry.action == "billing.reminder",
               AuditLogEntry.entity_name == key)
        .limit(1)
    ).first() is not None


def _days_until(moment: datetime, now: datetime) -> int:
    """Сколько суток осталось — вверх и не меньше одних: «через 0 дн.» не срок."""
    aware = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return max(1, ceil((aware - now) / timedelta(days=1)))


def _billing_letter(stage: str, sub: Subscription, organization: str,
                    now: datetime) -> mail.Letter:
    end = sub.current_period_end
    assert end is not None
    plan = get_plan(sub.plan_code, sub.product).name
    product = PRODUCT_NAME.get(sub.product, sub.product)
    link = mail.billing_url()
    if stage == "ending":
        return mail.period_ending_letter(
            organization=organization, product=product, plan=plan, ends=when_utc(end),
            days=_days_until(end, now), grace_days=GRACE_DAYS, link=link)
    if stage == "ended":
        grace_end = end + timedelta(days=GRACE_DAYS)
        return mail.period_ended_letter(
            organization=organization, product=product, plan=plan, ended=when_utc(end),
            grace_until=when_utc(grace_end), days_left=_days_until(grace_end, now),
            link=link)
    return mail.access_restricted_letter(organization=organization, product=product,
                                         plan=plan, link=link)


def send_billing_reminders(db: Session, now: datetime, *,
                           source: str = SOURCE_SCHEDULER) -> ReminderRun:
    """Разослать письма о деньгах: за неделю до конца периода, в день окончания и при
    закрытии записи (G4). Каждое — один раз на период.

    **Выключенная почта — «не пытались», а не «отправили»:** в журнал организации ничего
    не пишется, и когда почту включат, то же письмо уйдёт. **Неудача отправки** пишется
    отдельным действием (``billing.reminder_failed``) с причиной и повтор **не гасит**:
    письмо, которое не дошло, завтра попробуют снова.
    """
    run = ReminderRun()
    for sub in db.execute(select(Subscription)).scalars().all():
        stage = reminder_stage(sub.status, sub.current_period_end, now)
        if stage is None or not is_paid_plan(sub.plan_code):
            continue
        org_id = sub.organization_id
        key = _reminder_key(sub, stage)
        with as_tenant(db, org_id):
            if _already_sent(db, org_id, key):
                continue
            if not mail.mail_enabled():
                run.mail_off += 1
                continue
            recipients = _payers(db, org_id)
            if not recipients:
                run.no_recipients += 1
                continue
            organization = crud.get_organization(db, org_id)
            letter = _billing_letter(stage, sub,
                                     organization.name if organization else "", now)
            results = [(user.email, mail.send(user.email, letter)) for user in recipients]
            delivered = [email for email, sent in results if sent.ok]
            if delivered:
                crud.log_action(db, org_id, None, "billing.reminder",
                                entity_type="organization", entity_id=org_id,
                                entity_name=key,
                                details=f"{STAGE_LABEL[stage]}: письмо ушло "
                                        f"({len(delivered)} адресатам)")
                run.sent += 1
            else:
                reasons = "; ".join(sorted({sent.error for _, sent in results if sent.error}))
                crud.log_action(db, org_id, None, "billing.reminder_failed",
                                entity_type="organization", entity_id=org_id,
                                entity_name=key,
                                details=f"{STAGE_LABEL[stage]}: письмо не ушло — "
                                        f"{reasons or 'причина не названа'}")
                run.failed += 1
    record_run(db, "reminders", _reminder_summary(source, run))
    return run


def _reminder_summary(source: str, run: ReminderRun) -> str:
    parts = [f"писем ушло {run.sent}", f"не ушло {run.failed}"]
    if run.mail_off:
        parts.append(f"почта выключена — не отправлено {run.mail_off}")
    if run.no_recipients:
        parts.append(f"некому отправить {run.no_recipients}")
    return f"{source}: " + ", ".join(parts)
