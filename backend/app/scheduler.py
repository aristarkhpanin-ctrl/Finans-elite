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

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import billing, closing_docs, crud, job_state, mail
from .billing import ChargeResult, PaymentProvider, is_paid_plan
from .billing_period import (
    GRACE_DAYS,
    OVERDUE_STATUS,
    RENEW_MAX_ATTEMPTS,
    RENEW_RETRY_AFTER,
    days_overdue,
    effective_status,
    reminder_stage,
    renewal_due,
)
from .database import as_tenant
from .db_models import AuditLogEntry, Payment, StaffLogEntry, Subscription, User
from .plans import PRODUCT_NAME, Plan, get_plan
from .rbac import Perm, has_permission
from .timefmt import day_utc, when_utc

#: Задачи планировщика и их действие в служебном журнале. Перечень закрыт: экран
#: готовности читает ровно эти строки, и задача мимо перечня была бы невидимой.
TASKS: dict[str, str] = {
    "expire": "scheduler.expire",
    "reminders": "scheduler.reminders",
    "renew": "scheduler.renew",
    "acts": "scheduler.acts",
    "stuck": "scheduler.stuck",
}


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


#: Как часто пишется след у **частой** задачи, когда нового нет (G8). Каждый запуск
#: раз в десять минут утопил бы служебный журнал, а молчание журнала обязано значить
#: «не запускался»: тихий запуск пишет след, если прошлому больше этого.
QUIET_TRACE_EVERY = timedelta(hours=1)


def _wall_clock() -> datetime:
    """Настоящее время — им меряется давность следа (он записан настоящим временем)."""
    return datetime.now(timezone.utc)


def record_run(db: Session, task: str, details: str, *, quiet: bool = False) -> None:
    """След запуска в служебном журнале. Автора нет — это платформа, а не человек.

    ``quiet`` — запуску нечего сообщить: след пишется, только если прошлому следу этой
    задачи больше :data:`QUIET_TRACE_EVERY`. Запуск с новостью пишет всегда.
    """
    if quiet:
        last = last_runs(db).get(task)
        if last is not None and _wall_clock() - _aware(last) < QUIET_TRACE_EVERY:
            return
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

#: Письмо за неделю при включённом автопродлении — предупреждение о списании (G5).
#: Ключ у него тот же, что у обычного напоминания: одно письмо на конец периода.
NOTICE_LABEL = "предупреждение о предстоящем автосписании"


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


def _consent_problem(sub: Subscription, plan: Plan) -> str | None:
    """Почему данное согласие больше не покрывает списание (``None`` — покрывает).

    Одна проверка на два места — письмо за неделю и само списание: выросшую цену лучше
    назвать за неделю, чем в день списания, но и в день списания её обязаны поймать.
    """
    if plan.price_on_request or plan.price_rub <= 0:
        return "тариф не продлевается оплатой"
    amount = billing.checkout_amount(plan, sub.renew_months)
    if amount > sub.renew_amount_rub:
        return (f"цена выросла: согласие давалось на {mail.rub(sub.renew_amount_rub)}, "
                f"сейчас {mail.rub(amount)} — другую сумму без нового согласия не списываем")
    return None


def _billing_letter(stage: str, sub: Subscription, organization: str,
                    now: datetime, note: str = "") -> mail.Letter:
    end = sub.current_period_end
    assert end is not None
    plan_obj = get_plan(sub.plan_code, sub.product)
    plan = plan_obj.name
    product = PRODUCT_NAME.get(sub.product, sub.product)
    link = mail.billing_url()
    if stage == "ending" and sub.auto_renew:
        # При автопродлении письмо за неделю — то самое предупреждение, без которого
        # деньги не списываются: сумма, способ и как отказаться.
        return mail.renewal_notice_letter(
            organization=organization, product=product, plan=plan,
            amount=billing.checkout_amount(plan_obj, sub.renew_months),
            months=sub.renew_months, method=sub.payment_method_title,
            ends=when_utc(end), days=_days_until(end, now), link=link)
    if stage == "ending":
        return mail.period_ending_letter(
            organization=organization, product=product, plan=plan, ends=when_utc(end),
            days=_days_until(end, now), grace_days=GRACE_DAYS, link=link, note=note)
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
            note = ""
            if stage == "ending" and sub.auto_renew:
                problem = _consent_problem(sub, get_plan(sub.plan_code, sub.product))
                if problem:
                    crud.decline_auto_renew(db, sub, problem)
                    note = (f"Автопродление выключено: {problem}. Включить его снова "
                            "можно оплатой с отметкой согласия.")
            label = (NOTICE_LABEL if stage == "ending" and sub.auto_renew
                     else STAGE_LABEL[stage])
            organization = crud.get_organization(db, org_id)
            letter = _billing_letter(stage, sub,
                                     organization.name if organization else "", now,
                                     note=note)
            results = [(user.email, mail.send(user.email, letter)) for user in recipients]
            delivered = [email for email, sent in results if sent.ok]
            if delivered:
                crud.log_action(db, org_id, None, "billing.reminder",
                                entity_type="organization", entity_id=org_id,
                                entity_name=key,
                                details=f"{label}: письмо ушло "
                                        f"({len(delivered)} адресатам)")
                run.sent += 1
            else:
                reasons = "; ".join(sorted({sent.error for _, sent in results if sent.error}))
                crud.log_action(db, org_id, None, "billing.reminder_failed",
                                entity_type="organization", entity_id=org_id,
                                entity_name=key,
                                details=f"{label}: письмо не ушло — "
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


# --- Автопродление (G5) ---

@dataclass
class RenewalRun:
    """Итог запуска автопродления — по подпискам."""

    charged: int = 0       # списано, период продлён
    pending: int = 0       # ждёт итога от провайдера (в т.ч. исход неизвестен)
    failed: int = 0        # отказ с причиной; клиенту написано
    unknown: int = 0       # провайдер не ответил — повтора не будет
    not_warned: int = 0    # письмо-предупреждение не ушло: не списывали
    stopped: int = 0       # согласие погашено: цена выросла, тариф без срока
    blocked: int = 0       # автопродление на установке недоступно (нет оплаты/почты)


def _notify_payers(db: Session, org_id: str, letter: mail.Letter) -> str:
    """Письмо всем, кто вправе платить; итог — словами для журнала. Три состояния:
    не пытались (почта выключена), ушло, не ушло с причиной."""
    if not mail.mail_enabled():
        return "письмо не отправляли: почта выключена"
    recipients = _payers(db, org_id)
    if not recipients:
        return "письмо некому отправить"
    results = [mail.send(user.email, letter) for user in recipients]
    delivered = sum(1 for sent in results if sent.ok)
    if delivered:
        return f"письмо ушло ({delivered} адресатам)"
    reasons = "; ".join(sorted({sent.error for sent in results if sent.error}))
    return f"письмо не ушло — {reasons or 'причина не названа'}"


def settle_renewal(db: Session, payment: Payment, result: ChargeResult, *,
                   now: datetime | None = None) -> str:
    """Дописать итог автоматического списания: деньги, срок, журнал, письмо.

    **Одна дверь на два источника итога**: сам запуск (провайдер ответил сразу) и
    уведомление провайдера (ответил позже или не ответил вовсе). Две копии разошлись бы
    в первом же случае, который случается редко, — то есть там, где их никто не
    проверял бы. Возвращает исход для счётчиков запуска.
    """
    now = now or datetime.now(timezone.utc)
    org_id = payment.organization_id
    plan = get_plan(payment.plan_code)
    product = PRODUCT_NAME.get(plan.product, plan.product)
    sub = crud.get_subscription(db, org_id, plan.product)
    with as_tenant(db, org_id):
        organization = crud.get_organization(db, org_id)
        org_name = organization.name if organization else ""
        method = sub.payment_method_title if sub and sub.payment_method_title else "способ оплаты"
        link = mail.billing_url()

        if result.status == "succeeded":
            crud.mark_payment(db, payment, "succeeded")
            sub = billing.activate_paid_plan(db, org_id, plan, paid_at=now,
                                             months=payment.months, payment=payment)
            end = sub.current_period_end
            paid_until = when_utc(end) if end else "без срока"
            delivered = _notify_payers(db, org_id, mail.renewal_charged_letter(
                organization=org_name, product=product, plan=plan.name,
                amount=payment.amount_rub, months=payment.months, method=method,
                paid_until=paid_until, link=link))
            crud.log_action(db, org_id, None, "billing.auto_renew_charged",
                            entity_type="organization", entity_id=org_id,
                            entity_name=plan.code,
                            details=f"{plan.product}: списано {payment.amount_rub} ₽ за "
                                    f"{payment.months} мес., оплачено до {paid_until}; "
                                    f"{delivered}")
            return "charged"

        if sub is None:
            return "failed"
        if result.status == "pending":
            sub.renew_error = "Списание ждёт подтверждения провайдера."
            db.commit()
            return "pending"

        if result.status == "unknown":
            sub.renew_error = ("Провайдер не ответил — неизвестно, прошло ли списание. "
                               "Повторно не списываем, чтобы не взять деньги дважды; если "
                               "списания нет в выписке, оплатите вручную.")
            db.commit()
            delivered = _notify_payers(db, org_id, mail.renewal_unknown_letter(
                organization=org_name, product=product, plan=plan.name,
                amount=payment.amount_rub, method=method, link=link))
            crud.log_action(db, org_id, None, "billing.auto_renew_failed",
                            entity_type="organization", entity_id=org_id,
                            entity_name=plan.code,
                            details=f"{plan.product}: исход списания {payment.amount_rub} ₽ "
                                    f"неизвестен — {result.reason}; повтора не будет; "
                                    f"{delivered}")
            return "unknown"

        crud.mark_payment(db, payment, "canceled")
        attempt = sub.renew_attempts
        if result.method_unusable:
            crud.decline_auto_renew(db, sub, f"способ оплаты «{method}» больше не "
                                             f"принимается ({result.reason})")
            left = 0
        else:
            sub.renew_error = f"Списание не прошло: {result.reason}."
            db.commit()
            left = max(0, RENEW_MAX_ATTEMPTS - attempt)
        end = sub.current_period_end
        delivered = _notify_payers(db, org_id, mail.renewal_failed_letter(
            organization=org_name, product=product, plan=plan.name,
            amount=payment.amount_rub, method=method, reason=result.reason,
            next_try=day_utc(now + timedelta(days=1)), attempts_left=left,
            stopped=result.method_unusable, ends=when_utc(end) if end else "—",
            grace_days=GRACE_DAYS, link=link))
        crud.log_action(db, org_id, None, "billing.auto_renew_failed",
                        entity_type="organization", entity_id=org_id,
                        entity_name=plan.code,
                        details=f"{plan.product}: {payment.amount_rub} ₽ не списаны — "
                                f"{result.reason} (попытка {attempt} из "
                                f"{RENEW_MAX_ATTEMPTS}); {delivered}")
        return "failed"


def _renew(db: Session, provider: PaymentProvider, sub: Subscription,
           now: datetime) -> str:
    """Одно продление: проверки согласия, предупреждения и повтора — затем списание."""
    org_id = sub.organization_id
    end = sub.current_period_end
    assert end is not None and sub.payment_method_id is not None
    if crud.open_renewal_payment(db, org_id, end) is not None:
        return "pending"
    plan = get_plan(sub.plan_code, sub.product)
    problem = _consent_problem(sub, plan)
    if problem:
        # Названия берутся **до** погашения согласия: оно стирает и способ, и сумму.
        method = sub.payment_method_title or "способ оплаты"
        amount = (billing.checkout_amount(plan, sub.renew_months) if plan.price_rub > 0
                  else sub.renew_amount_rub)
        crud.decline_auto_renew(db, sub, problem)
        organization = crud.get_organization(db, org_id)
        delivered = _notify_payers(db, org_id, mail.renewal_failed_letter(
            organization=organization.name if organization else "",
            product=PRODUCT_NAME.get(sub.product, sub.product), plan=plan.name,
            amount=amount, method=method, reason=problem, next_try="", attempts_left=0,
            stopped=True, ends=when_utc(end), grace_days=GRACE_DAYS,
            link=mail.billing_url()))
        crud.log_action(db, org_id, None, "billing.auto_renew_failed",
                        entity_type="organization", entity_id=org_id,
                        entity_name=plan.code,
                        details=f"{sub.product}: не списано — {problem}; {delivered}")
        return "stopped"
    # Деньги не списываются без письма **до** них. Согласие включается только оплатой, а
    # оплата сдвигает конец периода, — поэтому письмо о конце **этого** периода либо
    # уже предупреждало о списании, либо не отправлялось вовсе.
    if not _already_sent(db, org_id, _reminder_key(sub, "ending")):
        sub.renew_error = ("Не списано: письмо о предстоящем списании не ушло, а без "
                           "предупреждения деньги не списываются. Оплатить можно вручную.")
        db.commit()
        return "not_warned"
    payers = _payers(db, org_id)
    if not payers:
        sub.renew_error = ("Не списано: некому отправить чек и письмо — нет действующего "
                           "участника с правом оплаты.")
        db.commit()
        return "not_warned"
    amount = billing.checkout_amount(plan, sub.renew_months)
    payment = crud.create_payment(db, org_id, plan.code, amount,
                                  provider=billing.provider_kind(provider),
                                  months=sub.renew_months, auto_renew_consent=True,
                                  renews_period_end=end)
    # Попытка засчитывается **до** обращения к провайдеру: упади процесс посреди
    # запроса, повтор через минуту был бы второй попыткой в те же сутки.
    sub.renew_attempts += 1
    sub.renew_attempted_at = now
    db.commit()
    result = provider.charge_saved(db, payment, plan, sub.payment_method_id, payers[0].email)
    return settle_renewal(db, payment, result, now=now)


def renew_subscriptions(db: Session, provider: PaymentProvider, now: datetime, *,
                        source: str = SOURCE_SCHEDULER) -> RenewalRun:
    """Списать продление тем, у кого включено автопродление и подходит срок (G5).

    Не больше одной попытки в сутки и трёх на один конец периода; пока исход прошлой
    неизвестен, новой нет. Запуск оставляет след всегда, как и остальные задачи.
    """
    run = RenewalRun()
    unavailable = billing.auto_renew_unavailable(provider)
    subs = db.execute(select(Subscription).where(
        Subscription.auto_renew.is_(True))).scalars().all()
    for sub in subs:
        if not sub.payment_method_id or not renewal_due(sub.current_period_end, now):
            continue
        if sub.renew_attempts >= RENEW_MAX_ATTEMPTS:
            continue
        last = sub.renew_attempted_at
        if last is not None and _aware(now) - _aware(last) < RENEW_RETRY_AFTER:
            continue
        if unavailable:
            sub.renew_error = f"Не списано: {unavailable}"
            db.commit()
            run.blocked += 1
            continue
        with as_tenant(db, sub.organization_id):
            outcome = _renew(db, provider, sub, now)
        setattr(run, outcome, getattr(run, outcome) + 1)
    record_run(db, "renew", _renewal_summary(source, run))
    return run


def _renewal_summary(source: str, run: RenewalRun) -> str:
    parts = [f"списано {run.charged}", f"не прошло {run.failed}"]
    for label, value in (("ждут провайдера", run.pending),
                         ("исход неизвестен", run.unknown),
                         ("не предупреждены — не списывали", run.not_warned),
                         ("согласие погашено", run.stopped),
                         ("автопродление недоступно", run.blocked)):
        if value:
            parts.append(f"{label} {value}")
    return f"{source}: " + ", ".join(parts)


# --- Акты оказанных услуг (G6) ---

@dataclass
class ActsRun:
    """Итог запуска: сколько актов составлено и почему не составлены остальные."""

    issued: int = 0
    blocked: int = 0       # реквизиты продавца или покупателя не готовы
    seller_problems: int = 0


def issue_acts(db: Session, now: datetime, *, source: str = SOURCE_SCHEDULER) -> ActsRun:
    """Составить акты по платежам, чей оплаченный период кончился (G6).

    Акт датируется окончанием периода: услуга оказана к нему, не раньше. Не готовы
    реквизиты — акт не составляется и **ждёт**: следующий запуск после их заполнения
    составит его той же датой окончания периода. След запуска — всегда, с причинами.
    """
    run = ActsRun()
    run.seller_problems = len(closing_docs.seller_problems())
    for payment in closing_docs.acts_due(db, now):
        org = crud.get_organization(db, payment.organization_id)
        if org is None:
            continue
        if run.seller_problems or closing_docs.buyer_problems(org):
            run.blocked += 1
            continue
        doc = closing_docs.issue_act(db, org, payment)
        with as_tenant(db, org.id):
            crud.log_action(db, org.id, None, "billing.act_issued",
                            entity_type="billing_document", entity_id=doc.id,
                            entity_name=closing_docs.title(doc),
                            details=f"{payment.amount_rub} ₽ — {closing_docs.service_line(doc)}")
        run.issued += 1
    parts = [f"актов составлено {run.issued}"]
    if run.blocked:
        parts.append(f"ждут реквизитов {run.blocked}"
                     + (" (реквизиты продавца заданы не полностью)"
                        if run.seller_problems else ""))
    record_run(db, "acts", f"{source}: " + ", ".join(parts))
    return run


# --- Зависшие задачи анализа (G8) ---

#: Порог «зависла», минуты. **По умолчанию выключено**: порог — решение эксплуатации
#: (фаза F отказалась от рассылки «с порогами, которых неоткуда взять»), и здесь его
#: задаёт человек.
STUCK_ENV = "STUCK_JOB_ALERT_MINUTES"


def stuck_threshold() -> tuple[int | None, str | None]:
    """Порог из окружения и почему он не применяется (``None`` — применяется либо не задан).

    Больше часа порог не бывает: состояние задачи Celery хранит час
    (``job_state.RESULT_TTL``), и после него «зависла» не отличить от «посчитана давно» —
    такой порог не сработал бы ни разу, а выглядел бы включённым.
    """
    raw = os.getenv(STUCK_ENV, "").strip()
    if not raw or raw == "0":
        return None, None
    try:
        minutes = int(raw)
    except ValueError:
        return None, f"{STUCK_ENV}=«{raw}» — не целое число минут; зависшие не проверяются"
    limit = int(job_state.RESULT_TTL.total_seconds() // 60)
    if not 1 <= minutes < limit:
        return None, (f"{STUCK_ENV}={minutes} — порог должен быть от 1 до {limit - 1} мин: "
                      f"состояние задачи хранится {limit} мин, и дольше «зависла» не "
                      "отличить от «посчитана давно»; зависшие не проверяются")
    return minutes, None


@dataclass
class StuckRun:
    threshold: int | None = None
    stuck: int = 0          # зависли дольше порога
    alerted: int = 0        # о скольких из них письмо ушло
    unknown: int = 0        # брокер не ответил — состояние неизвестно
    problem: str = ""       # почему проверка не шла или письмо не ушло


def _operators(db: Session) -> list[User]:
    """Кому писать о зависшем: операторы платформы, действующие и с адресом."""
    return [u for u in crud.list_staff(db)
            if u.staff_role == crud.STAFF_OPERATOR and u.blocked_at is None and u.email]


def _alerted(db: Session, job_id: str) -> bool:
    return db.execute(select(StaffLogEntry.id).where(
        StaffLogEntry.action == STUCK_ALERT_ACTION,
        StaffLogEntry.details.like(f"{job_id}:%")).limit(1)).first() is not None


#: Действие служебного журнала «о зависшей задаче написали» — по нему сверяется повтор.
STUCK_ALERT_ACTION = "jobs.stuck_alert"


def check_stuck_jobs(db: Session, now: datetime, *,
                     fetch: Callable[[str], tuple[str, object]],
                     source: str = SOURCE_SCHEDULER) -> StuckRun:
    """Найти задачи анализа, которые стоят в очереди или считаются дольше порога, и
    написать операторам — один раз на задачу (G8).

    Зависла — «в очереди» или «считается» дольше порога. **Упавшая — не зависла**: она
    уже сказала своё, и её видно на вкладке «Эксплуатация». **Молчание брокера — не
    зависла**, а «неизвестно»: писем о нём нет, след называет его. Смотрятся задачи не
    старше часа хранения состояния — старше их судьбу уже не узнать.
    """
    run = StuckRun()
    run.threshold, problem = stuck_threshold()
    if run.threshold is None:
        record_run(db, "stuck", f"{source}: " + (problem or "порог не задан — зависшие "
                                                  "задачи не проверяются; их видно на "
                                                  "вкладке «Эксплуатация»"), quiet=True)
        return run
    names = {o.id: o.name for o in crud.list_organizations(db, limit=1000)}
    fresh: list[tuple[str, str]] = []
    for job in crud.list_analysis_jobs(db, now - job_state.RESULT_TTL):
        state, _ = job_state.poll(job.id, fetch)
        verdict = job_state.interpret(state, created_at=job.created_at, now=now)
        if verdict.status == job_state.UNKNOWN:
            run.unknown += 1
            continue
        age = job_state.age_minutes(job.created_at, now)
        if verdict.status not in ("pending", "running") or age < run.threshold:
            continue
        run.stuck += 1
        if not _alerted(db, job.id):
            label = "в очереди" if verdict.status == "pending" else "считается"
            fresh.append((job.id, f"«{names.get(job.organization_id, '—')}»: {job.kind}, "
                                  f"{label} {age} мин"))
    if fresh:
        _alert(db, run, fresh)
    parts = [f"порог {run.threshold} мин", f"зависли {run.stuck}",
             f"письмо о новых ушло {run.alerted}"]
    if run.unknown:
        parts.append(f"состояние {run.unknown} неизвестно — хранилище результатов не "
                     "ответило")
    if run.problem:
        parts.append(run.problem)
    record_run(db, "stuck", f"{source}: " + ", ".join(parts),
               quiet=not (run.stuck or run.unknown or run.problem))
    return run


def _alert(db: Session, run: StuckRun, fresh: list[tuple[str, str]]) -> None:
    if not mail.mail_enabled():
        run.problem = "почта выключена — операторам не написали"
        return
    letter = mail.stuck_jobs_letter(jobs=[line for _, line in fresh],
                                    threshold=run.threshold or 0)
    recipients = [u for u in _operators(db) if u.email_verified_at is not None]
    if not recipients:
        run.problem = ("некому написать: нет действующего оператора с подтверждённым "
                       "адресом")
        return
    results = [mail.send(u.email, letter) for u in recipients]
    if not any(r.ok for r in results):
        reasons = "; ".join(sorted({r.error for r in results if r.error}))
        run.problem = f"письмо не ушло — {reasons or 'причина не названа'}"
        return
    for job_id, line in fresh:
        crud.log_staff_action(db, None, STUCK_ALERT_ACTION, details=f"{job_id}: {line}")
    run.alerted = len(fresh)
