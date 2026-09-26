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

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crud
from .billing_period import OVERDUE_STATUS, days_overdue, effective_status
from .database import as_tenant
from .db_models import StaffLogEntry, Subscription

#: Задачи планировщика и их действие в служебном журнале. Перечень закрыт: экран
#: готовности читает ровно эти строки, и задача мимо перечня была бы невидимой.
TASKS: dict[str, str] = {
    "expire": "scheduler.expire",
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
