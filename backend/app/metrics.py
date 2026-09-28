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

from .billing import is_paid_plan, parse_plan_change
from .billing_period import GRACE_DAYS, days_overdue
from .db_models import (
    Membership,
    Organization,
    Payment,
    Subscription,
    UsageEvent,
    User,
)
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


@dataclass(frozen=True)
class ChurnRecord:
    """Одна запись журнала об уходе, собранная обходом арендаторов.

    Организация названа, потому что отток считается **организациями**: одна и та же
    компания может просрочить подписку на оба продукта в один месяц, и сложить эти
    строки значило бы потерять одного клиента дважды.
    """

    organization_id: str
    action: str
    at: datetime
    details: str


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
    #: Записи журнала об уходе (F8) — тем же обходом, что и объёмы.
    churn_records: list[ChurnRecord] = field(default_factory=list)
    #: Когда по платформе впервые появилась запись каждого вида. Раньше этой даты ряд
    #: показывает «не измеряется»: ноль там означал бы «не уходили», а не «не записывали».
    first_churn_at: dict[str, datetime] = field(default_factory=dict)


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
class RevenuePoint:
    """Выручка одного месяца: сколько пришло и сколькими платежами.

    Считается **по дате платежа**, а не по периоду, за который платили: второе — это
    признание выручки, и оно требует учётной политики, которой у платформы нет. Говорить
    «выручка за март», имея в виду «деньги, пришедшие в марте», можно только назвав это.
    """

    month: str
    rub: int = 0
    payments: int = 0


@dataclass(frozen=True)
class ChurnPoint:
    """Отток одного месяца — **двумя картинами рядом** (F8).

    Журнал отвечает «что записано как случившееся», платежи — «кто платил и перестал».
    У картин разные пропуски, и свести их в одно число нельзя: среднее между «не
    запускали скрипт» и «денег не приходило» не значит ничего.

    ``None`` в ``expired`` и ``downgraded`` — «**не измеряется**», а не ноль: месяц
    раньше первой записи такого вида либо записи есть, но прежний тариф в них не назван.
    """

    month: str
    #: Не продлили оплаченный период (`billing.overdue`).
    expired: int | None = None
    #: Ушли на бесплатный сами (`billing.plan_change` с названным прежним платным).
    downgraded: int | None = None
    #: Платили в этом месяце — организаций (успешные платежи).
    payers: int = 0
    #: Из них перестали: последний успешный платёж пришёлся на этот месяц, а
    #: оплаченного периода с льготным сроком у организации больше нет.
    stopped: int = 0
    #: ``stopped / payers``. ``None`` — делить не на что (платящих в месяце не было).
    rate: float | None = None


@dataclass
class Churn:
    """Отток по месяцам плюс то, чего в этих числах нет."""

    months: list[ChurnPoint] = field(default_factory=list)
    #: Проводили ли сверку неоплаты хоть раз — планировщик или
    #: ``scripts/expire_subscriptions.py``. Нет — значит уход по
    #: окончании периода не измеряется вовсе, и это надо сказать, а не показать ноль.
    expiry_logged: bool = False
    #: Записи о смене тарифа, в которых прежний тариф не назван (сделаны до F8).
    unnamed_plan_changes: int = 0


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
    #: Выручка по месяцам — **только успешные** платежи (F2). Неуспешные видны в
    #: карточке клиента: там это разговор, здесь это не деньги.
    revenue: list[RevenuePoint] = field(default_factory=list)
    #: Отток (F8) — две картины рядом, а не одно число.
    churn: Churn = field(default_factory=Churn)
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


def revenue_by_month(db: Session, now: datetime, months: int) -> list[RevenuePoint]:
    """Выручка платформы по месяцам (F2).

    Суммируются **успешные** платежи: `pending` — это ещё не деньги, `canceled` — уже не
    деньги. Группировка в Python, как и рост: помесячная свёртка на диалекте SQL прошла
    бы тесты на SQLite и разошлась бы с PostgreSQL молча.

    Пустой месяц остаётся в ряду с нулём — пропуск читался бы как потерянные данные.
    """
    window = _months_back(now, months)
    totals: dict[str, RevenuePoint] = {m: RevenuePoint(month=m) for m in window}
    earliest = window[0]
    for payment in db.scalars(select(Payment).where(Payment.status == "succeeded")):
        stamp = _as_utc(payment.created_at)
        month = _month(stamp) if stamp else ""
        if month < earliest or month not in totals:
            continue
        totals[month].rub += int(payment.amount_rub or 0)
        totals[month].payments += 1
    return [totals[m] for m in window]


def _covered(first_at: datetime | None, month: str) -> bool:
    """Застал ли ряд этот месяц. ``None`` первой записи — не застал вовсе."""
    stamp = _as_utc(first_at)
    return stamp is not None and month >= _month(stamp)


def churn(db: Session, now: datetime, months: int, *, totals: TenantTotals) -> Churn:
    """Отток по месяцам — **двумя картинами, которые не сводятся в одну** (F8).

    Определение записано заранее и не меняется (OPEN-DECISIONS §1): отток — организация,
    у которой **была платная** подписка и не стало. Триал, не ставший платным, — воронка,
    а не отток; смешать их значит получить число, которым нельзя пользоваться.

    **Картина 1 — журнал**: что записано как случившееся. Не продлили оплаченный период
    (`billing.overdue`, запись оставляет скрипт эксплуатации) и ушли на бесплатный сами
    (`billing.plan_change`, у которой назван прежний тариф). Записей нет — значит **не
    измеряется**, и ряд говорит это словом, а не нулём: скрипт запускает эксплуатация, и
    его молчание ничего не говорит о клиентах.

    **Картина 2 — платежи**: кто платил и перестал. Последний успешный платёж пришёлся
    на месяц, а оплаченного периода с льготным сроком у организации больше нет.

    Делить одну картину на другую нельзя, и здесь этого нет: доля считается **внутри**
    платежей (перестали / платили). Журнал записывает уходы, но не население, и частное
    от деления «записанных уходов» на «плативших» было бы ровно тем сведением двух картин
    в одно число, от которого метрику и уберегали.

    Считается **организациями**, а не подписками: клиент, отказавшийся от одного продукта
    и оставшийся на другом, ушедшим не считается. Иначе картины считали бы разные единицы
    (платёж один на организацию) и перестали бы быть сравнимыми.
    """
    window = _months_back(now, months)
    expired: dict[str, set[str]] = {m: set() for m in window}
    downgraded: dict[str, set[str]] = {m: set() for m in window}
    unreadable: dict[str, set[str]] = {m: set() for m in window}
    unnamed = 0

    for record in totals.churn_records:
        stamp = _as_utc(record.at)
        month = _month(stamp) if stamp else ""
        if month not in expired:
            continue
        if record.action == "billing.overdue":
            expired[month].add(record.organization_id)
            continue
        parsed = parse_plan_change(record.details)
        if parsed is None:
            # Прежний тариф не назван (запись сделана до F8): уход это или переключение
            # бесплатного на бесплатный — из неё не видно, и гадать метрика не станет.
            unnamed += 1
            unreadable[month].add(record.organization_id)
            continue
        _, was, became = parsed
        if is_paid_plan(was) and not is_paid_plan(became):
            downgraded[month].add(record.organization_id)

    payers, stopped = _payment_churn(db, now, window)
    first_overdue = totals.first_churn_at.get("billing.overdue")
    first_change = totals.first_churn_at.get("billing.plan_change")

    points: list[ChurnPoint] = []
    for month in window:
        left: int | None = len(expired[month]) if _covered(first_overdue, month) else None
        if not _covered(first_change, month):
            went_free: int | None = None
        elif not downgraded[month] and unreadable[month]:
            # Записи в месяце есть, но читаемых среди них нет: ноль сказал бы «никто не
            # уходил сам», а правда — «по этим записям не видно».
            went_free = None
        else:
            went_free = len(downgraded[month])
        paid_count, left_count = len(payers[month]), len(stopped[month])
        points.append(ChurnPoint(
            month=month, expired=left, downgraded=went_free,
            payers=paid_count, stopped=left_count,
            rate=(left_count / paid_count) if paid_count else None))
    return Churn(months=points, expiry_logged=first_overdue is not None,
                 unnamed_plan_changes=unnamed)


def _payment_churn(db: Session, now: datetime,
                   window: list[str]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """«Платил и перестал» — вторая картина оттока, целиком из платежей и подписок.

    Уход отнесён к месяцу **последнего платежа**, а не к месяцу, когда кончился
    оплаченный период: «перестал платить» — это про платёж, которого не было, и датировать
    его можно только последним, который был.

    «Перестал» проверяется по подписке, а не по календарю от даты платежа: оплату за
    несколько периодов сразу (оплата по счёту, F1) числом месяцев платформа в платеже не
    хранит, зато ``current_period_end`` его уже учёл — и организация внутри оплаченного
    периода ушедшей не считается, сколько бы месяцев назад она ни платила.
    """
    payers: dict[str, set[str]] = {m: set() for m in window}
    last_paid: dict[str, str] = {}
    for org_id, created in db.execute(
            select(Payment.organization_id, Payment.created_at)
            .where(Payment.status == "succeeded")):
        stamp = _as_utc(created)
        if stamp is None:
            continue
        month = _month(stamp)
        if month in payers:
            payers[month].add(org_id)
        if month > last_paid.get(org_id, ""):
            last_paid[org_id] = month
    # Организации, у которых оплаченный период (с льготным сроком) ещё идёт хоть по
    # одному продукту: они платят, и ушедшими их называть нечем.
    paying_now = {
        org_id for org_id, end in db.execute(
            select(Subscription.organization_id, Subscription.current_period_end))
        if end is not None and days_overdue(end, now) <= GRACE_DAYS
    }
    stopped: dict[str, set[str]] = {m: set() for m in window}
    for org_id, month in last_paid.items():
        if month in stopped and org_id not in paying_now:
            stopped[month].add(org_id)
    return payers, stopped


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
        revenue=revenue_by_month(db, now, months),
        churn=churn(db, now, months, totals=totals),
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
    else:
        # Пока подписка не кончалась, «оформлена» и «действует» были одним и тем же.
        # Теперь это разные вещи, и срез по тарифам отвечает на первый вопрос, не на второй.
        notes.append(
            "Срез по тарифам считает **оформленные** подписки, включая те, у которых "
            "оплаченный период уже закончился: «на каком тарифе организация» и «платит "
            "ли она сейчас» — разные вопросы, и второй этот срез не задаёт.")
    notes.append(
        "Воронка активации отвечает «дошла ли организация до шага **когда-нибудь**», а не "
        "«за период»: дошла в прошлом году — тоже дошла.")
    if any(point.rub for point in metrics.revenue):
        notes.append(
            "Выручка — это **деньги, пришедшие в месяце**, а не выручка периода, за "
            "который платили: признание по периодам требует учётной политики, которой у "
            "платформы нет. Считаются только успешные платежи; возвратов платформа не "
            "учитывает вовсе — механизма возврата в продукте нет, и вычесть их неоткуда. "
            "Тариф «по запросу» суммы не имеет и в выручку не попадает.")
    else:
        notes.append(
            "Успешных платежей за окно не было: ноль здесь означает «денег не приходило», "
            "а не «не считали». Оплата по счёту попадает сюда, только если её провёл "
            "оператор — назначением тарифа; прямые переводы мимо продукта платформа не "
            "видит.")
    notes.extend(_churn_notes(metrics.churn, totals))
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


def _churn_notes(data: Churn, totals: TenantTotals) -> list[str]:
    """Чего нет в числах оттока. Половина работы этого пункта — здесь.

    Отток — метрика, которой пользуются, чтобы принимать решения о продукте, и каждый её
    пропуск читается как благополучие: ноль ушедших выглядит ровно как «никто не уходит».
    """
    notes = [
        "Отток — организация, у которой **была платная** подписка и не стало. Триал, не "
        "ставший платным, сюда не входит: это воронка, а не отток, и смешать их значит "
        "получить число, которым нельзя пользоваться.",
        "Две картины оттока **не сводятся в одно число**: журнал отвечает «что записано "
        "как случившееся», платежи — «кто платил и перестал». Пропуски у них разные, и "
        "среднее между ними не значило бы ничего.",
        "Считается организациями, а не подписками: клиент, отказавшийся от одного "
        "продукта и оставшийся на другом, ушедшим не считается — иначе картины считали "
        "бы разные единицы (платёж один на организацию) и перестали бы быть сравнимыми.",
    ]
    if not data.expiry_logged:
        notes.append(
            "Уход по окончании оплаченного периода **не измеряется**: записей "
            "`billing.overdue` в журнале нет вовсе — сверку неоплаты ни разу не "
            "проводили: ни планировщик (процесс beat не запущен), ни вручную "
            "`scripts/expire_subscriptions.py`. Ноль здесь означал бы «никто не "
            "уходит», а это другое утверждение.")
    else:
        first = _as_utc(totals.first_churn_at.get("billing.overdue"))
        assert first is not None      # expiry_logged ровно это и означает
        notes.append(
            f"Уход по окончании периода виден с {first.strftime('%m.%Y')} — раньше стоит "
            "«не измеряется»: запись оставляет сверка неоплаты (планировщик или скрипт "
            "эксплуатации), и до её первого запуска её неоткуда было взять.")
    if data.unnamed_plan_changes:
        notes.append(
            f"В {data.unnamed_plan_changes} записях о смене тарифа прежний тариф не "
            "назван (сделаны до того, как журнал стал его писать): ушла организация с "
            "платного или переключила бесплатный на бесплатный — из них не видно. В "
            "отток они не взяты, а месяц, где других записей нет, показывает «не "
            "измеряется».")
    notes.append(
        "«Платил и перестал» отнесён к месяцу **последнего платежа**, а не к месяцу, "
        "когда кончился оплаченный период. Последние месяцы ещё могут вырасти: у части "
        "плативших оплаченный период с льготным сроком не истёк, и ушедшими они пока не "
        "считаются.")
    notes.append(
        "Организация, **закрывшая себя** (выгрузка и удаление), из обеих картин исчезает: "
        "её журнал и её платежи удаляются вместе с ней. Факт закрытия остаётся в "
        "служебном журнале, но платила ли она — оттуда не видно.")
    notes.append(
        "Назначение тарифа платформой (оплата по счёту) в отток не входит ни в одну "
        "сторону: это её действие, а не решение клиента. Прекращение такой оплаты видно "
        "по окончании периода — на общих основаниях.")
    return notes


def product_label(product: str) -> str:
    return PRODUCT_NAME.get(product, product)
