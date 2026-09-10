"""Сводка платформы: сколько у нас клиентов и что они делают (B3).

**Второй системы учёта не заводим.** Числа собираются из того, что уже есть: таблиц
организаций, пользователей, членства и подписок — и из журнала действий. Счётчики,
заведённые «под метрики», начинают жить своей жизнью: расходятся с данными, и разбирать
потом приходится не бизнес, а расхождение.

Отсюда же и главное ограничение, которое здесь важнее самих цифр: **платформа умеет
считать не всё, и об этом сказано в самом ответе**. Счётчика расчётов нет; отметка
присутствия появилась не с первого дня; журнал начинается с первой записи, а не с начала
времён. Каждая такая граница едет вместе с числом (``notes``) — иначе ноль до её начала
читается как «ничего не происходило».

Группировка по месяцам делается **в Python, а не в SQL**: у SQLite это ``strftime``, у
PostgreSQL — ``to_char``, и диалектный запрос прошёл бы тесты (SQLite) и упал бы в
продакшене (PostgreSQL) — или, что хуже, посчитал бы иначе и молча.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db_models import Membership, Organization, Subscription, User
from .plans import PRODUCT_NAME, get_plan

#: Окна активности. Семь дней отвечают на вопрос «пользуются ли сейчас», тридцать —
#: «не ушли ли». Одно окно вместо двух заставило бы выбирать между этими вопросами.
ACTIVE_WINDOWS = (7, 30)


@dataclass(frozen=True)
class MonthPoint:
    """Сколько появилось за месяц. Накопленный итог не хранится: его считает тот, кто
    рисует, и хранить обе величины значило бы завести возможность их расхождения."""

    period: str          # «2026-09»
    organizations: int
    users: int


@dataclass(frozen=True)
class PlanSlice:
    product: str
    plan_code: str
    plan_name: str
    organizations: int


@dataclass
class TenantTotals:
    """Итоги, собранные обходом арендаторов (их считает служебный роутер).

    Живут отдельным типом, потому что собираются иначе, чем всё остальное: проекты, дела
    и журнал под RLS, и платформа входит в каждую организацию по очереди — обхода
    изоляции у неё нет (B1). ``organizations_scanned`` говорит, по скольким организациям
    свод построен: усечённый обход обязан назвать себя, иначе неполная сумма выглядит
    как измеренная.
    """

    projects: int = 0
    cases: int = 0
    calculated: int = 0
    exports: int = 0
    first_log_at: datetime | None = None
    organizations_scanned: int = 0
    organizations_total: int = 0


@dataclass
class PlatformMetrics:
    generated_at: datetime
    since_days: int
    organizations: int = 0
    users: int = 0
    active_users: dict[int, int] = field(default_factory=dict)
    active_organizations: dict[int, int] = field(default_factory=dict)
    #: Участники, у которых отметки присутствия нет вовсе. Это «неизвестно», а не
    #: «не работают»: до появления отметки (A3) присутствие не записывалось.
    members_without_mark: int = 0
    projects: int = 0
    cases: int = 0
    projects_calculated: int = 0
    exports: int = 0
    growth: list[MonthPoint] = field(default_factory=list)
    plans: list[PlanSlice] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _month(value: datetime) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _months_back(now: datetime, months: int) -> list[str]:
    """Подписи месяцев по возрастанию, включая текущий.

    Месяцы, в которые ничего не появилось, **остаются в ряду с нулём**: выброшенный
    пустой месяц превращает провал в графике в ровную линию — то есть врёт ровно там,
    где смотреть интереснее всего.
    """
    out: list[str] = []
    year, month = now.year, now.month
    for _ in range(months):
        out.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(out))


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite отдаёт наивное время; сравнивать его с осведомлённым — ошибка времени
    выполнения, а не расхождение чисел, поэтому приводим в одном месте."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def monthly_growth(db: Session, now: datetime, months: int = 12) -> list[MonthPoint]:
    """Сколько организаций и пользователей появлялось по месяцам."""
    periods = _months_back(now, months)
    orgs: dict[str, int] = {p: 0 for p in periods}
    users: dict[str, int] = {p: 0 for p in periods}
    for (created,) in db.execute(select(Organization.created_at)):
        key = _month(_as_utc(created) or now)
        if key in orgs:
            orgs[key] += 1
    for (created,) in db.execute(select(User.created_at)):
        key = _month(_as_utc(created) or now)
        if key in users:
            users[key] += 1
    return [MonthPoint(period=p, organizations=orgs[p], users=users[p]) for p in periods]


def plan_slices(db: Session) -> list[PlanSlice]:
    """Сколько организаций на каком тарифе — по каждому продукту.

    Считаются **оформленные подписки**: организация без подписки работает на тарифе по
    умолчанию, но приписать её к нему здесь значило бы смешать «выбрал бесплатный» с
    «не выбирал ничего» — разные разговоры с клиентом (то же различие, что и в карточке).
    """
    rows = db.execute(
        select(Subscription.product, Subscription.plan_code, func.count())
        .group_by(Subscription.product, Subscription.plan_code)
    ).all()
    out = [
        PlanSlice(product=product, plan_code=code,
                  plan_name=get_plan(code, product).name, organizations=int(count))
        for product, code, count in rows
    ]
    return sorted(out, key=lambda s: (s.product, s.plan_code))


def _activity(db: Session, now: datetime) -> tuple[dict[int, int], dict[int, int], int]:
    """Активные пользователи и организации по окнам + участники без отметки.

    Активность читается из ``Membership.last_seen_at`` — той же отметки, что видит
    администратор организации (A3). Второй источник дал бы два разных ответа на вопрос
    «работает ли человек», и оба выглядели бы одинаково правдоподобно.
    """
    rows = [(user_id, org_id, _as_utc(seen)) for user_id, org_id, seen in
            db.execute(select(Membership.user_id, Membership.organization_id,
                              Membership.last_seen_at)).all()]
    without_mark = sum(1 for _, _, seen in rows if seen is None)
    users: dict[int, int] = {}
    orgs: dict[int, int] = {}
    for days in ACTIVE_WINDOWS:
        edge = now - timedelta(days=days)
        fresh = [(user_id, org_id) for user_id, org_id, seen in rows
                 if seen is not None and seen >= edge]
        # Человек считается один раз, даже если работал в трёх организациях: иначе
        # «активных пользователей» окажется больше, чем пользователей.
        users[days] = len({user_id for user_id, _ in fresh})
        orgs[days] = len({org_id for _, org_id in fresh})
    return users, orgs, without_mark


def build_platform_metrics(db: Session, *, totals: TenantTotals, now: datetime | None = None,
                           months: int = 12, since_days: int = 30) -> PlatformMetrics:
    """Собрать сводку платформы. ``totals`` приходит снаружи — см. :class:`TenantTotals`."""
    now = now or datetime.now(timezone.utc)
    active_users, active_orgs, without_mark = _activity(db, now)
    metrics = PlatformMetrics(
        generated_at=now,
        since_days=since_days,
        organizations=int(db.scalar(select(func.count()).select_from(Organization)) or 0),
        users=int(db.scalar(select(func.count()).select_from(User)) or 0),
        active_users=active_users,
        active_organizations=active_orgs,
        members_without_mark=without_mark,
        projects=totals.projects,
        cases=totals.cases,
        projects_calculated=totals.calculated,
        exports=totals.exports,
        growth=monthly_growth(db, now, months),
        plans=plan_slices(db),
    )
    metrics.notes = _notes(metrics, totals)
    return metrics


def _notes(metrics: PlatformMetrics, totals: TenantTotals) -> list[str]:
    """Чего эти числа **не** значат. Едет вместе с ними — в ответ, на экран и в файл.

    Оговорка, оставленная в документации, до того, кто смотрит на график, не доходит;
    а неназванный пробел читается как благополучие: ноль выгрузок за период, которого
    журнал не застал, выглядит ровно как ноль выгрузок.
    """
    notes = [
        f"«Считали» — сколько проектов открывали с расчётом за {metrics.since_days} дн., "
        "а не сколько было расчётов: счётчика расчётов платформа не ведёт.",
        "Выгрузки — документы «Элит» и «Аудита»; выгрузка журнала организации сюда не "
        "входит.",
    ]
    if metrics.members_without_mark:
        notes.append(
            f"У {metrics.members_without_mark} участников отметки присутствия нет вовсе — "
            "это «неизвестно», а не «не работают»: отметка ведётся не с первого дня.")
    first_log = _as_utc(totals.first_log_at)
    if first_log is None:
        notes.append("Журнал действий пуст: выгрузки считать не из чего.")
    else:
        notes.append(
            f"Журнал ведётся с {first_log.strftime('%d.%m.%Y')} — за более ранние даты "
            "выгрузок не видно, и ноль там означает «не записывали».")
    if totals.organizations_scanned < totals.organizations_total:
        notes.append(
            f"Объёмы и выгрузки посчитаны по {totals.organizations_scanned} организациям "
            f"из {totals.organizations_total}: обход арендаторов ограничен.")
    if not metrics.plans:
        notes.append("Подписок никто не оформлял: все работают на тарифе по умолчанию.")
    return notes


def product_label(product: str) -> str:
    return PRODUCT_NAME.get(product, product)
