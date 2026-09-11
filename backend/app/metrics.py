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

from .db_models import Membership, Organization, Subscription, UsageEvent, User
from .plans import DEFAULT_PLAN, PRODUCT_NAME, get_plan
from .usage import collecting as usage_collecting

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
    #: Сколько организаций дошло до шага воронки (E3). Считается при том же обходе
    #: арендаторов, что и объёмы: второй обход ради тех же чисел был бы вдвое дороже и
    #: однажды разошёлся бы с первым.
    with_entities: int = 0
    with_calculation: int = 0
    with_export: int = 0


@dataclass
class FunnelStep:
    """Шаг воронки активации: сколько организаций дошло и какая доля от начала."""

    key: str
    label: str
    organizations: int = 0
    #: Доля от первого шага. ``None`` — считать не от чего (нет ни одной организации).
    share: float | None = None


@dataclass
class RetentionPoint:
    """Когорта: сколько из пришедших в этот месяц вернулись позже.

    ``returned`` = ``None`` означает «**не измеряется**», а не ноль: удержание считается
    по событиям пользования (E2), и в месяцы, когда сбор был выключен, знать его неоткуда.
    Ноль здесь читался бы как «все ушли» — это другое утверждение.
    """

    month: str
    arrived: int = 0
    returned: int | None = None


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
    #: Воронка активации. Считается **всегда**: три первых шага доступны из журнала и
    #: дат расчёта, событий для них не требуется.
    funnel: list[FunnelStep] = field(default_factory=list)
    #: Удержание по когортам. Пусто, если сбор событий не велся: график из воздуха
    #: хуже отсутствующего.
    retention: list[RetentionPoint] = field(default_factory=list)
    #: Собираются ли события пользования (E2) — чтобы экран не гадал, почему пусто.
    usage_collected: bool = False
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


def activation_funnel(db: Session, totals: TenantTotals) -> list[FunnelStep]:
    """Воронка активации: зарегистрировался → завёл → посчитал → выгрузил → оплатил.

    Считается **из уже существующего**: организации, их проекты и дела, даты последнего
    расчёта и записи журнала о выгрузках. Событий (E2) для этого не нужно — поэтому
    воронка есть и в установках, где сбор выключен.

    Шага «открыл результаты» в ней нет намеренно: отдельного маршрута у этого экрана не
    существует, он зовёт расчёт, и шаг был бы вторым именем предыдущего.
    """
    organizations = int(db.scalar(select(func.count()).select_from(Organization)) or 0)
    paid = int(db.scalar(
        select(func.count(func.distinct(Subscription.organization_id)))
        .where(Subscription.plan_code != DEFAULT_PLAN)) or 0)
    steps = [
        FunnelStep("signup", "Завели организацию", organizations),
        FunnelStep("created", "Завели проект или дело", totals.with_entities),
        FunnelStep("calculated", "Посчитали хотя бы раз", totals.with_calculation),
        FunnelStep("exported", "Выгрузили документ", totals.with_export),
        FunnelStep("paid", "Перешли на платный тариф", paid),
    ]
    base = steps[0].organizations
    for step in steps:
        step.share = (step.organizations / base) if base else None
    return steps


def retention(db: Session, now: datetime, months: int) -> list[RetentionPoint]:
    """Удержание по когортам месяца регистрации — **только по событиям** (E2).

    До появления событий это не считалось вовсе: отметка присутствия хранит одно
    последнее значение, и «вернулся ли человек через неделю» из неё не выводится. Там,
    где событий нет, стоит ``None`` — «не измеряется», а не ноль: ноль читался бы как
    «все ушли».
    """
    rows = db.execute(select(UsageEvent.organization_id, UsageEvent.event,
                             UsageEvent.created_at)).all()
    if not rows:
        return []
    arrived: dict[str, str] = {}          # организация → месяц первого события
    seen: dict[str, set[str]] = {}        # организация → месяцы, когда была активность
    for org_id, event, created in rows:
        stamp = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        month = _month(stamp)
        seen.setdefault(org_id, set()).add(month)
        if event == "signup":
            arrived[org_id] = month
        elif org_id not in arrived or month < arrived[org_id]:
            arrived.setdefault(org_id, month)
    out: list[RetentionPoint] = []
    for month in _months_back(now, months):
        cohort = [org for org, first in arrived.items() if first == month]
        if not cohort:
            out.append(RetentionPoint(month=month, arrived=0, returned=None))
            continue
        came_back = sum(1 for org in cohort if any(m > month for m in seen.get(org, ())))
        out.append(RetentionPoint(month=month, arrived=len(cohort), returned=came_back))
    return out


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
        funnel=activation_funnel(db, totals),
        retention=retention(db, now, months),
        usage_collected=usage_collecting(),
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
    notes.append(
        "Воронка активации отвечает «дошла ли организация до шага **когда-нибудь**», а не "
        "«за период»: дошла в прошлом году — тоже дошла.")
    if not metrics.usage_collected:
        notes.append(
            "События пользования не собираются (`USAGE_EVENTS` выключен), поэтому "
            "удержание **не измеряется**: отметка присутствия хранит только последнее "
            "значение, и «вернулся ли человек через неделю» из неё не выводится. Пустой "
            "график здесь честнее нарисованного.")
    elif not metrics.retention:
        notes.append(
            "События собираются, но когорт ещё нет: удержание появится, когда пройдёт "
            "хотя бы один месяц после первых регистраций.")
    else:
        notes.append(
            "Удержание считается по событиям пользования и только с того момента, как их "
            "начали собирать: у месяцев до этого стоит «не измеряется», а не ноль.")
    return notes


def product_label(product: str) -> str:
    return PRODUCT_NAME.get(product, product)
