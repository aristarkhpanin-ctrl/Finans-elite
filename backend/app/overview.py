"""Сводка организации на одном экране (ADMIN-PHASE-F, F7).

Администратор клиента видел участников, активность и журнал — и не видел того, что
спрашивают чаще всего: сколько у нас проектов и дел, сколько ещё можно завести, когда
кончается оплаченный период. Ответы были разложены по трём экранам и одному отказу
402, который приходил уже в момент сохранения.

**Ни счётчика, ни таблицы.** Всё это платформа уже считает — `crud.org_volumes`,
`billing.units_used`, `billing_period`, `access.restriction_for`, — и сводка их
**складывает**, а не пересчитывает. Второй источник любого из этих чисел однажды
разошёлся бы с первым, и клиент получил бы две правды: «осталось 2» на экране и 402 при
сохранении.

Правила пустоты — те же, что в B3, и они едут **вместе с числами**:

* «без предела» — это **не ноль**: у корпоративного тарифа квоты нет вовсе, и `None`
  здесь значит «не ограничено», а не «ничего нельзя»;
* расчётов платформа **не считает** — счётчика нет, показывается дата последнего;
* участник без отметки присутствия — **«неизвестно»**, а не «не работает»: отметки
  появились с A3, и у тех, кто не заходил после неё, её нет по устройству;
* **приостановленный участник место в квоте занимает** — иначе администратор
  приостанавливает сотрудника, ждёт свободного места и не понимает, почему его нет.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import billing, crud
from .access import restriction_for
from .billing_period import GRACE_DAYS, days_overdue, effective_status, grace_days_left
from .db_models import Membership
from .plans import PRODUCT_NAME, PRODUCTS, UNIT_NAME


@dataclass
class ProductState:
    """Состояние одного продукта: тариф, квота, срок, ограничение.

    ``units_limit`` / ``members_limit`` равны ``None``, когда предела нет вовсе. Это
    **не ноль**: подставить сюда число значило бы показать корпоративному клиенту
    «осталось 0» ровно там, где ему можно всё.
    """

    product: str
    product_name: str
    plan_code: str
    plan_name: str
    #: Оформлена ли подписка вообще. ``none`` — «не оформляли», а не «бесплатный тариф».
    status: str
    unit_name: str
    units_used: int = 0
    units_limit: int | None = None
    units_left: int | None = None
    members_limit: int | None = None
    members_left: int | None = None
    period_end: datetime | None = None
    #: Дней до конца оплаченного периода. ``None`` — периода нет («не истекает»).
    days_left: int | None = None
    #: Дней льготного срока, если период уже кончился. ``None`` — льготный не идёт.
    grace_left: int | None = None
    #: Почему продукт ограничен — тем же текстом, каким отказывает сохранение.
    restriction_kind: str = ""
    restriction_reason: str = ""
    restriction_remedy: str = ""
    restriction_blocking: bool = False


@dataclass
class Overview:
    """Организация одним взглядом. Оговорки — часть ответа, а не украшение."""

    name: str = ""
    created_at: datetime | None = None
    projects: int = 0
    cases: int = 0
    groups: int = 0
    holdings: int = 0
    members: int = 0
    members_blocked: int = 0
    #: Сколько участников без отметки присутствия: **«неизвестно»**, а не «не работают».
    members_unknown: int = 0
    last_calculated_at: datetime | None = None
    last_seen_at: datetime | None = None
    products: list[ProductState] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _left(limit: int | None, used: int) -> int | None:
    """Сколько осталось. ``None`` при отсутствии предела — и ноль не подставляется."""
    return None if limit is None else max(0, limit - used)


def _days_left(period_end: datetime | None, now: datetime) -> int | None:
    """Дней до конца оплаченного периода. ``None`` — периода нет; ноль — кончился."""
    if period_end is None:
        return None
    end = period_end if period_end.tzinfo is not None \
        else period_end.replace(tzinfo=timezone.utc)
    return max(0, (end - now).days)


def build_overview(db: Session, org_id: str, now: datetime | None = None) -> Overview:
    """Собрать сводку организации из того, что платформа уже считает.

    Зовётся **внутри арендатора** (маршрут входит в организацию, как её участник):
    половина этих таблиц под RLS, и запрос без него вернул бы на PostgreSQL пустоту.
    """
    now = now or datetime.now(timezone.utc)
    org = crud.get_organization(db, org_id)
    volumes = crud.org_volumes(db, org_id)
    unknown = int(db.scalar(
        select(crud.func.count()).select_from(Membership)
        .where(Membership.organization_id == org_id,
               Membership.last_seen_at.is_(None))) or 0)

    out = Overview(
        name=org.name if org else "",
        created_at=org.created_at if org else None,
        members_unknown=unknown,
        **volumes,
    )

    for product in PRODUCTS:
        sub = crud.get_subscription(db, org_id, product)
        plan = billing.current_plan(db, org_id, product)
        used = billing.units_used(db, org_id, product)
        period_end = sub.current_period_end if sub else None
        overdue = days_overdue(period_end, now)
        state = ProductState(
            product=product,
            product_name=PRODUCT_NAME.get(product, product),
            plan_code=plan.code,
            plan_name=plan.name,
            # Состояние **выводится**, а не читается из поля: хранимое «действует» у
            # подписки с истёкшим сроком — не ответ на вопрос «работает ли она сейчас».
            status=effective_status(sub.status, period_end, now) if sub else "none",
            unit_name=UNIT_NAME.get(product, "объектов"),
            units_used=used,
            units_limit=plan.max_units,
            units_left=_left(plan.max_units, used),
            members_limit=plan.max_members,
            members_left=_left(plan.max_members, volumes["members"]),
            period_end=period_end,
            days_left=_days_left(period_end, now),
            grace_left=grace_days_left(period_end, now) if 0 < overdue <= GRACE_DAYS
            else None,
        )
        restriction = restriction_for(db, org_id, product)
        if restriction is not None:
            state.restriction_kind = restriction.kind
            state.restriction_reason = restriction.reason
            state.restriction_remedy = restriction.remedy
            state.restriction_blocking = restriction.blocking
        out.products.append(state)

    out.notes = _notes(out)
    return out


def _notes(out: Overview) -> list[str]:
    """Что эти числа **не** значат. Едут с ними на экран, а не лежат в документации."""
    notes = [
        "«Считали» платформа не считает: счётчика расчётов нет — расчёт идёт при каждом "
        "открытии результатов и в журнал не пишется. Показана дата последнего расчёта.",
    ]
    if any(p.units_limit is None or p.members_limit is None for p in out.products):
        notes.append("«Без предела» — это не ноль: у такого тарифа квоты нет вовсе.")
    if out.members_unknown:
        notes.append(
            f"У {out.members_unknown} из {out.members} участников нет отметки "
            "присутствия — это «неизвестно», а не «не работает»: отметки ведутся не с "
            "самого начала, и у тех, кто не заходил после, её нет по устройству.")
    if out.members_blocked:
        notes.append(
            f"Приостановленные участники ({out.members_blocked}) место в квоте "
            "занимают: приостановка закрывает доступ, но не освобождает место — "
            "освобождает удаление из организации.")
    if out.last_calculated_at is None and out.projects:
        notes.append("Ни один проект ещё не считали — это не ошибка, а состояние.")
    return notes
