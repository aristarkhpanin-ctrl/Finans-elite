"""Pydantic-схемы ответа API и преобразование из ``CalcResult``.

Decimal сериализуется в JSON как строка (точность сохраняется), ``None`` → ``null``.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from audit_core import AuditSubjectModel
from calc_core import ProjectModel
from calc_core.reports.result import CalcResult
from calc_core.reports.statements import Statement


class LineOut(BaseModel):
    code: str
    label: str
    values: list[Decimal]


class StatementOut(BaseModel):
    lines: list[LineOut]


class MetricsOut(BaseModel):
    npv: Decimal
    irr_annual: Optional[Decimal] = None
    mirr_annual: Optional[Decimal] = None
    arr_annual: Optional[Decimal] = None
    pi: Optional[Decimal] = None
    pb_months: Optional[int] = None
    dpb_months: Optional[int] = None
    pv_investments: Optional[Decimal] = None
    peak_financing_need: Optional[Decimal] = None


class RatiosOut(BaseModel):
    liquidity: dict[str, list[Optional[Decimal]]]
    activity: dict[str, list[Optional[Decimal]]]
    gearing: dict[str, list[Optional[Decimal]]]
    profitability: dict[str, list[Optional[Decimal]]]
    investment: dict[str, list[Optional[Decimal]]]


class BreakEvenOut(BaseModel):
    break_even_revenue: list[Optional[Decimal]]
    margin_of_safety: list[Optional[Decimal]]


class ValuationOut(BaseModel):
    net_assets: Decimal
    gordon_value: Optional[Decimal] = None
    dividend_value: Optional[Decimal] = None
    earnings_multiple_value: Optional[Decimal] = None
    liquidation_value: Optional[Decimal] = None


class StageBudgetOut(BaseModel):
    id: str
    name: str
    kind: str
    start_month: int
    finish_month: int
    cost: Decimal
    # Актуализация (план-факт, gap 4.6); None — этап не актуализирован.
    actual_start_month: Optional[int] = None
    actual_finish_month: Optional[int] = None
    actual_cost: Optional[Decimal] = None
    cost_variance: Optional[Decimal] = None
    schedule_variance_months: Optional[int] = None
    # Финансовый разрез этапа: освоение и оплата по месяцам + трактовка в отчётах.
    monthly: list[Decimal] = []
    monthly_cash: list[Decimal] = []
    treatment: str = "none"        # expense | deferred | asset | mixed | none


class BudgetOut(BaseModel):
    """Смета по этапам календарного плана + помесячные графики и итоги.

    Финансовый разрез: освоение (``monthly``) и оплата (``monthly_cash``) — разные ряды,
    их накопленный разрыв (``payables``) равен кредиторке B23; итоги по трактовке
    показывают, куда стоимость попадёт в отчётах.
    """

    stages: list[StageBudgetOut] = []
    monthly: list[Decimal] = []
    total: Decimal = Decimal(0)
    actual_total: Optional[Decimal] = None
    monthly_cash: list[Decimal] = []
    cumulative: list[Decimal] = []
    cumulative_cash: list[Decimal] = []
    payables: list[Decimal] = []
    expense_total: Decimal = Decimal(0)
    deferred_total: Decimal = Decimal(0)
    asset_total: Decimal = Decimal(0)


def budget_response(budget) -> "BudgetOut":
    """Собрать смету-ответ из ``calc_core.reports.result.Budget``."""
    return BudgetOut(
        stages=[StageBudgetOut(
            id=s.id, name=s.name, kind=s.kind, start_month=s.start_month,
            finish_month=s.finish_month, cost=s.cost,
            actual_start_month=s.actual_start_month, actual_finish_month=s.actual_finish_month,
            actual_cost=s.actual_cost, cost_variance=s.cost_variance,
            schedule_variance_months=s.schedule_variance_months,
            monthly=list(s.monthly), monthly_cash=list(s.monthly_cash),
            treatment=s.treatment)
            for s in budget.stages],
        monthly=list(budget.monthly),
        total=budget.total,
        actual_total=budget.actual_total,
        monthly_cash=list(budget.monthly_cash),
        cumulative=list(budget.cumulative),
        cumulative_cash=list(budget.cumulative_cash),
        payables=list(budget.payables),
        expense_total=budget.expense_total,
        deferred_total=budget.deferred_total,
        asset_total=budget.asset_total,
    )


class ProductMarginOut(BaseModel):
    """Маржа продукта по рецептуре (BOM): выручка − материалы − сдельная ЗП проданного."""

    product_id: str
    name: str
    revenue: Decimal
    bom_cost: Decimal
    piece_wages: Decimal
    margin: Decimal
    margin_share: Optional[Decimal] = None


class ProductMarginsOut(BaseModel):
    products: list[ProductMarginOut] = []
    # Суммовые (глобальные) прямые издержки — не распределяются по продуктам.
    unallocated_direct: Decimal = Decimal(0)


class DivisionMarginOut(BaseModel):
    """Маржа подразделения (gap 4.5): свёртка маржи продуктов бизнес-единицы."""

    division_id: str
    name: str
    revenue: Decimal
    bom_cost: Decimal
    piece_wages: Decimal
    margin: Decimal
    margin_share: Optional[Decimal] = None
    product_count: int


class UserRowOut(BaseModel):
    """Вычисленная строка таблицы пользователя (при ошибке формулы — error + нули)."""

    name: str
    values: list[Decimal] = []
    error: Optional[str] = None


class UserTableOut(BaseModel):
    id: str
    name: str
    rows: list[UserRowOut] = []


class ParticipantOut(BaseModel):
    """Доходы участника финансирования: поток, вложено/получено, NPV/IRR (± терминальная)."""

    id: str
    name: str
    kind: str                                   # equity | lender
    flow: list[Decimal] = []
    invested: Decimal = Decimal(0)
    withdrawn: Decimal = Decimal(0)
    npv: Decimal = Decimal(0)
    irr_annual: Optional[Decimal] = None
    terminal_value: Optional[Decimal] = None
    npv_with_terminal: Optional[Decimal] = None
    irr_with_terminal_annual: Optional[Decimal] = None


class LineDetailItemOut(BaseModel):
    """Слагаемое строки отчёта (drill-down): источник и его помесячный ряд."""

    name: str
    values: list[Decimal] = []


class LineDetailOut(BaseModel):
    """Детализация строки отчёта по источникам (Σ слагаемых = строка отчёта)."""

    code: str
    items: list[LineDetailItemOut] = []


class CalcResponse(BaseModel):
    engine_version: str
    n: int
    income: StatementOut
    cashflow: StatementOut
    balance: StatementOut
    profit_use: StatementOut
    metrics: MetricsOut
    # Показатели во второй валюте (SPEC §17); None, если ставка по валюте не задана.
    metrics_foreign: Optional[MetricsOut] = None
    ratios: RatiosOut
    break_even: BreakEvenOut
    valuation: ValuationOut
    budget: BudgetOut = BudgetOut()
    product_margins: ProductMarginsOut = ProductMarginsOut()
    # Маржа по подразделениям (gap 4.5); пусто без подразделений.
    division_margins: list[DivisionMarginOut] = []
    user_tables: list[UserTableOut] = []
    # Детализация ключевых строк отчётов (drill-down, пакет №6); пустая без данных.
    details: list[LineDetailOut] = []
    # Доходы участников финансирования (пакет №7); пусто без финансирования.
    participants: list[ParticipantOut] = []
    actualized_cashflow: Optional[StatementOut] = None
    cashflow_variance: Optional[StatementOut] = None
    warnings: list[str]


# --- Ревью бизнес-плана (Ф10, вне паритета с Project Expert) ---

class FindingOut(BaseModel):
    """Одна находка ревью: severity + человекочитаемый текст + числовое обоснование."""

    id: str
    category: str          # viability | liquidity | structure | assumptions | divergence
    severity: str          # info | warning | risk
    title: str
    detail: str
    recommendation: str
    confidence: str = "high"   # high | medium | low
    evidence: dict = Field(default_factory=dict)


class ReviewResponse(BaseModel):
    light: str                        # ok | info | warning | risk («светофор»)
    counts: dict[str, int]            # число находок по severity
    findings: list[FindingOut] = []
    # Прогонялась ли стохастика (Монте-Карло + чувствительность) для категории divergence.
    deep: bool = False
    # Экспертное заключение — связный автотекст из находок и показателей (пакет №5).
    opinion: str = ""


def review_response(review, *, deep: bool, opinion: str = "") -> "ReviewResponse":
    """Собрать ответ ревью из результата ядра (``calc_core.review.ReviewResult``)."""
    return ReviewResponse(
        light=review.light,
        counts=review.counts,
        findings=[FindingOut(
            id=f.id, category=f.category, severity=f.severity, title=f.title,
            detail=f.detail, recommendation=f.recommendation, confidence=f.confidence,
            evidence=f.evidence,
        ) for f in review.findings],
        deep=deep,
        opinion=opinion,
    )


# --- Проекты (персистентность, 6.1) ---

class ProjectCreate(BaseModel):
    name: str
    model: ProjectModel


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[ProjectModel] = None


class LastCalcOut(BaseModel):
    """Сводка последнего успешного расчёта (B1)."""

    npv: Decimal
    irr_annual: Optional[Decimal] = None
    pb_months: Optional[int] = None
    engine_version: str
    calculated_at: datetime


class ProjectSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    last_calc: Optional[LastCalcOut] = None
    # Модель менялась после последнего расчёта (или расчёта не было) → «Черновик».
    is_stale: bool = True
    # Гейт финализации (Ф10): "draft" | "finalized"; момент финализации.
    status: str = "draft"
    finalized_at: Optional[datetime] = None


class ProjectOut(ProjectSummary):
    model: ProjectModel
    # Снимок ревью, которым план был подтверждён при финализации (NULL — не финализирован).
    finalized_review: Optional[ReviewResponse] = None
    # Модель изменилась после финализации (отпечаток не совпадает) — снимок устарел.
    finalized_drift: bool = False


class FinalizeRequest(BaseModel):
    """Запрос финализации: acknowledge подтверждает осознание risk-находок (снятие гейта)."""

    acknowledge: bool = False


class FinalizeResponse(BaseModel):
    """Результат финализации: статус проекта + ревью, которым план подтверждён."""

    status: str
    finalized_at: datetime
    review: ReviewResponse


# --- Версии проекта (пакет №8, gap 4.4) ---

class VersionCreate(BaseModel):
    """Запрос снимка текущей модели как именованной версии."""

    label: str = ""


class VersionSummary(BaseModel):
    """Метаданные версии (без модели): для списка версий проекта."""

    id: str
    label: str
    created_at: datetime
    npv: Optional[Decimal] = None
    irr_annual: Optional[Decimal] = None
    engine_version: Optional[str] = None


class VersionOut(VersionSummary):
    """Версия с полной моделью снимка."""

    model: ProjectModel


class ModelChangeOut(BaseModel):
    """Изменение листового значения модели между версиями."""

    path: str
    kind: str                     # added | removed | changed
    old: object = None
    new: object = None


class MetricChangeOut(BaseModel):
    """Изменение показателя эффективности между версиями."""

    key: str
    label: str
    old: Optional[Decimal] = None
    new: Optional[Decimal] = None


class VersionDiffOut(BaseModel):
    """Анализ изменений: диф модели (листовые пути) + диф заголовочных показателей."""

    base_id: str                  # с чего сравниваем (id версии)
    against: str                  # с чем: id версии или "current"
    model_changes: list[ModelChangeOut] = []
    model_changes_truncated: bool = False
    metric_changes: list[MetricChangeOut] = []


# --- Организации, пользователи, членство (мультиарендность, 6.2) ---

class OrganizationCreate(BaseModel):
    name: str


class OrganizationOut(BaseModel):
    id: str
    name: str
    created_at: datetime


class OrganizationMembershipOut(BaseModel):
    id: str
    name: str
    role: str
    created_at: datetime


class MemberCreate(BaseModel):
    email: str
    full_name: str = ""
    role: str = "viewer"


class MemberPatch(BaseModel):
    role: str


class AuditLogEntryOut(BaseModel):
    """Запись журнала действий: кто, что, над чем и когда.

    ``actor_email`` берётся из журнала, а не из таблицы пользователей: участника могли
    удалить, а журнал обязан отвечать «кто это сделал» и после его ухода.
    """

    id: str
    actor_email: str
    action: str
    entity_type: str = ""
    entity_id: str = ""
    entity_name: str = ""
    details: str = ""
    created_at: datetime


class AuditLogPage(BaseModel):
    """Страница журнала: записи (новые сверху) и общее их число в организации."""

    entries: list[AuditLogEntryOut] = []
    total: int = 0


class MemberOut(BaseModel):
    """Участник организации.

    ``invite_token`` заполняется **только в ответе на приглашение** и только если
    участник ещё не заводил пароль: это одноразовая ссылка активации, которую
    пригласивший передаёт лично (почтовой отправки у платформы нет). В списке
    участников его нет — там он был бы вечно доступным пропуском в чужой аккаунт.
    """

    user_id: str
    email: str
    full_name: str
    role: str
    invite_token: Optional[str] = None


# --- Аутентификация (6.3) ---

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""
    organization_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str


class ActivateRequest(BaseModel):
    """Активация приглашения: по токену задать пароль и войти."""

    token: str
    password: str
    full_name: str = ""


class ProfileUpdate(BaseModel):
    full_name: str = Field(default="", max_length=255)


class PasswordChange(BaseModel):
    """Смена своего пароля. Текущий обязателен — иначе украденная сессия меняет пароль."""

    current_password: str
    new_password: str


# --- Тарифы и подписка (биллинг, 6.5) ---

class PlanOut(BaseModel):
    """Тариф каталога. Единица квоты зависит от продукта: проект у «Элит», дело у «Аудита».

    Поэтому поле называется ``max_units``, а не ``max_projects``: имя, верное лишь для
    половины каталога, однажды прочитают буквально. ``unit_name`` даёт подпись для экрана.
    """

    code: str
    product: str                        # business | audit
    name: str
    price_rub: int
    #: Цена «по запросу»: корпоративные условия не выражаются числом, и ноль вместо них
    #: выглядел бы как бесплатный тариф.
    price_on_request: bool = False
    max_units: Optional[int] = None
    unit_name: str = "проектов"
    max_members: Optional[int] = None


class SubscriptionOut(BaseModel):
    """Подписка организации на один продукт: тариф, статус и использование квот."""

    product: str = "business"
    plan_code: str
    plan_name: str
    status: str
    current_period_end: Optional[datetime] = None
    price_rub: int = 0
    price_on_request: bool = False
    max_units: Optional[int] = None
    unit_name: str = "проектов"
    max_members: Optional[int] = None
    used_units: int = 0
    used_members: int


class SubscriptionUpdate(BaseModel):
    plan_code: str


class CheckoutRequest(BaseModel):
    plan_code: str
    return_url: str = "https://example.com/billing/return"


class CheckoutResponse(BaseModel):
    activated: bool
    payment_id: Optional[str] = None
    confirmation_url: Optional[str] = None


# --- Анализ чувствительности (7.3) ---

class SensitivityRequest(BaseModel):
    param: str
    factors: list[Decimal] = [Decimal("0.8"), Decimal("0.9"), Decimal("1.0"),
                              Decimal("1.1"), Decimal("1.2")]


class SensitivityPointOut(BaseModel):
    factor: Decimal
    npv: Decimal
    irr_annual: Optional[Decimal] = None


class SensitivityResponse(BaseModel):
    param: str
    points: list[SensitivityPointOut]


# --- Монте-Карло (7.4) ---

class DistributionIn(BaseModel):
    kind: str  # uniform | normal | triangular
    low: Optional[Decimal] = None
    high: Optional[Decimal] = None
    mean: Optional[Decimal] = None
    std: Optional[Decimal] = None
    mode: Optional[Decimal] = None


class UncertainParamIn(BaseModel):
    param: str
    distribution: DistributionIn


class MonteCarloRequest(BaseModel):
    iterations: int = 500
    seed: int = 42
    uncertain: list[UncertainParamIn] = []


class HistogramBinOut(BaseModel):
    """Столбец гистограммы NPV (B5); ``from_`` сериализуется как ``from``."""

    from_: Decimal = Field(serialization_alias="from")
    to: Decimal
    count: int

    model_config = {"populate_by_name": True}


class MonteCarloResponse(BaseModel):
    iterations: int
    npv_mean: Decimal
    npv_std: Decimal
    npv_sem: Decimal           # стандартная ошибка среднего = σ/√N
    npv_min: Decimal
    npv_max: Decimal
    npv_p5: Decimal            # VaR 95% (5-й перцентиль)
    npv_p10: Decimal
    npv_p50: Decimal
    npv_p90: Decimal
    npv_p95: Decimal
    npv_cvar_5: Decimal        # CVaR/ES 95% (среднее худших 5%)
    probability_npv_positive: Decimal
    histogram: list[HistogramBinOut] = []


def monte_carlo_response(res) -> "MonteCarloResponse":
    """Собрать ответ Монте-Карло из результата ядра (общий код для sync и фоновой задачи)."""
    return MonteCarloResponse(
        iterations=res.iterations, npv_mean=res.npv_mean, npv_std=res.npv_std,
        npv_sem=res.npv_sem, npv_min=res.npv_min, npv_max=res.npv_max,
        npv_p5=res.npv_p5, npv_p10=res.npv_p10, npv_p50=res.npv_p50,
        npv_p90=res.npv_p90, npv_p95=res.npv_p95, npv_cvar_5=res.npv_cvar_5,
        probability_npv_positive=res.probability_npv_positive,
        histogram=[HistogramBinOut(from_=b.from_, to=b.to, count=b.count) for b in res.histogram],
    )


# --- Фоновые задачи анализа (Celery) ---

class JobSubmitResponse(BaseModel):
    job_id: str
    status: str = "pending"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str                                # pending | running | success | failure
    result: MonteCarloResponse | None = None   # заполнено при status=success
    error: str | None = None                   # заполнено при status=failure


# --- What-If (9.1) ---

class ScenarioAdjustmentIn(BaseModel):
    param: str
    factor: Decimal


class ScenarioIn(BaseModel):
    name: str
    adjustments: list[ScenarioAdjustmentIn] = []


class WhatIfRequest(BaseModel):
    scenarios: list[ScenarioIn] = []
    include_base: bool = True


class ScenarioResultOut(BaseModel):
    name: str
    npv: Decimal
    irr_annual: Optional[Decimal] = None
    pi: Optional[Decimal] = None
    pb_months: Optional[int] = None


class WhatIfResponse(BaseModel):
    scenarios: list[ScenarioResultOut]


# --- Integrator (9.2) ---

class ConsolidateRequest(BaseModel):
    project_ids: list[str]
    group_discount_rate: Decimal = Decimal("0.15")


# --- PIC Holding (9.3) ---

class HoldingCreate(BaseModel):
    name: str


class HoldingMemberCreate(BaseModel):
    project_id: str
    role: str = "subsidiary"  # parent | subsidiary


class HoldingMemberOut(BaseModel):
    project_id: str
    role: str


class HoldingConsolidationOut(BaseModel):
    """Сводка последней консолидации холдинга (B3)."""

    npv: Decimal
    rate: Decimal
    at: datetime


class HoldingOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    members: list[HoldingMemberOut] = []
    last_consolidation: Optional[HoldingConsolidationOut] = None


class HoldingMemberPatch(BaseModel):
    role: str  # parent | subsidiary


class PerProjectOut(BaseModel):
    """Вклад одного проекта в консолидацию (B3)."""

    project_id: str
    name: str
    role: str
    npv: Decimal
    irr_annual: Optional[Decimal] = None
    revenue_total: Decimal
    net_profit_total: Decimal


class ConsolidateResponse(CalcResponse):
    """Сводный бюджет холдинга + разбивка вклада по проектам (B3)."""

    per_project: list[PerProjectOut] = []


def _statement_out(s: Statement) -> StatementOut:
    return StatementOut(
        lines=[LineOut(code=code, label=s.labels[code], values=s[code]) for code in s.order]
    )


def to_response(r: CalcResult) -> CalcResponse:
    """Преобразовать результат ядра в схему ответа API."""
    return CalcResponse(
        engine_version=r.engine_version,
        n=r.n,
        income=_statement_out(r.income),
        cashflow=_statement_out(r.cashflow),
        balance=_statement_out(r.balance),
        profit_use=_statement_out(r.profit_use),
        metrics=MetricsOut(
            npv=r.metrics.npv,
            irr_annual=r.metrics.irr_annual,
            mirr_annual=r.metrics.mirr_annual,
            arr_annual=r.metrics.arr_annual,
            pi=r.metrics.pi,
            pb_months=r.metrics.pb_months,
            dpb_months=r.metrics.dpb_months,
            pv_investments=r.metrics.pv_investments,
            peak_financing_need=r.metrics.peak_financing_need,
        ),
        metrics_foreign=MetricsOut(
            npv=r.metrics_foreign.npv,
            irr_annual=r.metrics_foreign.irr_annual,
            mirr_annual=r.metrics_foreign.mirr_annual,
            arr_annual=r.metrics_foreign.arr_annual,
            pi=r.metrics_foreign.pi,
            pb_months=r.metrics_foreign.pb_months,
            dpb_months=r.metrics_foreign.dpb_months,
            pv_investments=r.metrics_foreign.pv_investments,
            peak_financing_need=r.metrics_foreign.peak_financing_need,
        ) if r.metrics_foreign is not None else None,
        ratios=RatiosOut(
            liquidity=r.ratios.liquidity,
            activity=r.ratios.activity,
            gearing=r.ratios.gearing,
            profitability=r.ratios.profitability,
            investment=r.ratios.investment,
        ),
        break_even=BreakEvenOut(
            break_even_revenue=r.break_even.break_even_revenue,
            margin_of_safety=r.break_even.margin_of_safety,
        ),
        valuation=ValuationOut(
            net_assets=r.valuation.net_assets,
            gordon_value=r.valuation.gordon_value,
            dividend_value=r.valuation.dividend_value,
            earnings_multiple_value=r.valuation.earnings_multiple_value,
            liquidation_value=r.valuation.liquidation_value,
        ),
        budget=budget_response(r.budget),
        user_tables=[UserTableOut(
            id=t.id, name=t.name,
            rows=[UserRowOut(name=row.name, values=list(row.values), error=row.error)
                  for row in t.rows],
        ) for t in r.user_tables],
        product_margins=ProductMarginsOut(
            products=[ProductMarginOut(
                product_id=p.product_id, name=p.name, revenue=p.revenue, bom_cost=p.bom_cost,
                piece_wages=p.piece_wages, margin=p.margin, margin_share=p.margin_share,
            ) for p in r.product_margins.products],
            unallocated_direct=r.product_margins.unallocated_direct,
        ),
        division_margins=[DivisionMarginOut(
            division_id=d.division_id, name=d.name, revenue=d.revenue, bom_cost=d.bom_cost,
            piece_wages=d.piece_wages, margin=d.margin, margin_share=d.margin_share,
            product_count=d.product_count,
        ) for d in r.division_margins],
        details=[LineDetailOut(
            code=d.code,
            items=[LineDetailItemOut(name=i.name, values=list(i.values)) for i in d.items],
        ) for d in r.details],
        participants=[ParticipantOut(
            id=p.id, name=p.name, kind=p.kind, flow=list(p.flow),
            invested=p.invested, withdrawn=p.withdrawn, npv=p.npv,
            irr_annual=p.irr_annual, terminal_value=p.terminal_value,
            npv_with_terminal=p.npv_with_terminal,
            irr_with_terminal_annual=p.irr_with_terminal_annual,
        ) for p in r.participants],
        actualized_cashflow=_statement_out(r.actualized_cashflow) if r.actualized_cashflow else None,
        cashflow_variance=_statement_out(r.cashflow_variance) if r.cashflow_variance else None,
        warnings=r.warnings,
    )


# --- Субъекты анализа (Финанс-Аудит, продукт №2) ---

class AuditSubjectCreate(BaseModel):
    name: str
    model: AuditSubjectModel


class AuditSubjectUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[AuditSubjectModel] = None


class AuditSubjectSummary(BaseModel):
    """Метаданные субъекта: число периодов и сходимость баланса (актив = пассив)."""

    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    n_periods: int = 0
    balanced: bool = True
    industry: str = ""
    #: Сводный «светофор» диагностики последнего периода: ok | warning | risk.
    #: ``None`` — отчётности нет, диагностика не считалась. Это разные факты, и
    #: подставлять вместо «не считалось» зелёный «ok» нельзя: список дел показывал бы
    #: благополучие там, где данных просто не вводили.
    light: Optional[str] = None


class AuditSubjectOut(AuditSubjectSummary):
    model: AuditSubjectModel
    # Актив − пассив по периодам (0 — сходится); строки-Decimal (точность без float).
    balance_gap: list[Decimal] = []


class AuditLineOut(BaseModel):
    """Строка аналитической формы (подытоги помечены ``subtotal``)."""

    code: str
    label: str
    values: list[Decimal] = []
    subtotal: bool = False


class AuditTrendOut(BaseModel):
    """Горизонтальный анализ строки: Δ и темп к предыдущему периоду (первый — база)."""

    code: str
    label: str
    delta: list[Optional[Decimal]] = []
    rate: list[Optional[Decimal]] = []


class AuditShareOut(BaseModel):
    """Вертикальный анализ: доля строки в базе периода (актив / выручка)."""

    code: str
    label: str
    share: list[Optional[Decimal]] = []


class AuditScoreOut(BaseModel):
    """Скоринговая модель банкротства: балл и зона по периодам (None — нет данных)."""

    id: str
    name: str
    values: list[Optional[Decimal]] = []
    zones: list[Optional[str]] = []       # safe | grey | distress
    note: str = ""


class AuditAssessmentOut(BaseModel):
    """Оценка показателя по нормативам: статус по периодам (good | warn | risk)."""

    group: str
    name: str
    status: list[Optional[str]] = []


class AuditDiagnosticsOut(BaseModel):
    """Диагностика: скоринги, оценка нормативов и сводный «светофор»."""

    light: str = "ok"                      # ok | warning | risk
    summary: str = ""
    scores: list[AuditScoreOut] = []
    assessments: list[AuditAssessmentOut] = []


class AuditUserMetricOut(BaseModel):
    """Пользовательский показатель: ряд по периодам (при ошибке формулы — error + нули)."""

    name: str
    values: list[Decimal] = []
    error: Optional[str] = None


class AuditAnalysisOut(BaseModel):
    """Результат анализа фактической отчётности (Финанс-Аудит)."""

    n: int
    periods: list[str] = []
    balance: list[AuditLineOut] = []
    income: list[AuditLineOut] = []
    horizontal: list[AuditTrendOut] = []
    vertical: list[AuditShareOut] = []
    ratios: dict[str, dict[str, list[Optional[Decimal]]]] = {}
    balance_gap: list[Decimal] = []
    balanced: bool = True
    # Диагностика (фаза D); None при пустой модели.
    diagnostics: Optional[AuditDiagnosticsOut] = None
    # Пользовательские показатели (фаза G); пусто без методик.
    user_metrics: list[AuditUserMetricOut] = []
    # Числа получены после переоценки статей (v2) — не «как в отчётности».
    revalued: bool = False
    # Экспертное заключение — связный автотекст по результату анализа (фаза E).
    opinion: str = ""
    warnings: list[str] = []
    # Качество ввода («Экран 19»): находки о самих данных, а не о финансовом состоянии.
    # В AuditResult не входят — анализ и высказывание о его входе это разные вещи.
    input_issues: list["AuditInputIssueOut"] = []
    # Реестр красных флагов («Экран 9»); в AuditResult не входит — см. SPEC, Прил. И.
    flags: "AuditFlagsOut" = None  # type: ignore[assignment]
    # Качество прибыли («Экран 7»); в AuditResult не входит — см. SPEC, Прил. К.
    earnings: "AuditEarningsOut" = None  # type: ignore[assignment]
    # Реестр обязательств и залогов («Экран 10»); в AuditResult не входит — SPEC, Прил. Л.
    obligations: "AuditObligationsOut" = None  # type: ignore[assignment]
    # Чек-лист процедур («Экран 21»); в AuditResult не входит — SPEC, Прил. М.
    procedures: "AuditProceduresOut" = None  # type: ignore[assignment]
    # Сводка дела и вердикт («Экран 1»); в AuditResult не входит — SPEC, Прил. Н.
    summary: "AuditSummaryOut" = None  # type: ignore[assignment]
    # Оценка стоимости («Экран 4»); в AuditResult не входит — SPEC, Прил. П.
    valuation: "AuditValuationOut" = None  # type: ignore[assignment]


class AuditAdjustmentOut(BaseModel):
    """Применённая поправка нормализации: что, почему и на сколько."""

    label: str
    kind: str
    kind_label: str
    amounts: list[Decimal] = []
    total: Decimal = Decimal(0)


class AuditEarningsOut(BaseModel):
    """Нормализация показателя прибыли.

    ``base_code`` — что именно нормализовано: EBITDA (введена амортизация) или EBIT.
    Показывать это имя обязательно: два показателя различаются на всю амортизацию, и
    мультипликатор, применённый не к тому, ошибётся ровно на неё.
    """

    base_code: str = "EBIT"
    reported: list[Decimal] = []
    normalized: list[Decimal] = []
    adjustments: list[AuditAdjustmentOut] = []
    grade: Optional[str] = None            # A | B | C; None — сравнивать не с чем
    grade_note: str = ""
    deviation: Optional[Decimal] = None


class AuditFlagOut(BaseModel):
    """Красный флаг: что настораживает, в каких периодах и на сколько рублей."""

    code: str
    severity: str                      # risk | warning
    title: str
    detail: str
    periods: list[int] = []
    #: Денежная мера. ``None`` — её не существует, а не «ноль рублей».
    impact: Optional[Decimal] = None
    evidence: dict[str, Decimal] = {}


class AuditFlagsOut(BaseModel):
    """Реестр флагов с честным итогом: сумма оценённых + число неоценённых.

    Без ``unpriced`` итог выглядел бы полной ценой рисков, хотя часть рисков в него
    не вошла — денежной меры у них нет вовсе.
    """

    flags: list[AuditFlagOut] = []
    priced_total: Decimal = Decimal(0)
    unpriced: int = 0


class AuditObligationRowOut(BaseModel):
    """Строка реестра обязательств: введённое + то, что следует из вида обязательства."""

    creditor: str
    contract: str
    kind: str
    kind_label: str
    off_balance: bool
    amount: Decimal
    rate: Optional[Decimal] = None       # None — ставка не указана (≠ беспроцентный)
    maturity: str                        # «2029» | «по требованию» | «срок не указан»
    on_demand: bool = False
    collateral: str = ""
    pledged_amount: Decimal = Decimal(0)
    covenant: str = ""
    covenant_status: str = "unknown"     # ok | breached | unknown
    covenant_note: str = ""


class AuditMaturityBucketOut(BaseModel):
    """Сколько долга упирается в год погашения (не платёж года — график не вводится)."""

    label: str
    amount: Decimal
    kind: str = "year"                   # year | on_demand | unknown


class AuditObligationsOut(BaseModel):
    """Реестр обязательств: два несводимых итога + сверка с балансом (SPEC, Прил. Л).

    ``balance_debt`` и ``off_balance`` намеренно не имеют общей суммы: условное
    обязательство ещё не наступило, и сложение утверждало бы обратное.
    """

    rows: list[AuditObligationRowOut] = []
    balance_debt: Decimal = Decimal(0)
    off_balance: Decimal = Decimal(0)
    reported_debt: Decimal = Decimal(0)  # P_LONG + P_SHORT последнего периода
    discrepancy: Decimal = Decimal(0)    # отчётность − реестр
    reconciled: bool = True
    buckets: list[AuditMaturityBucketOut] = []
    pledged_total: Decimal = Decimal(0)
    free_assets: Optional[Decimal] = None    # None — активов нет, сравнивать не с чем
    pledged_share: Optional[Decimal] = None
    covenants_breached: int = 0
    covenants_unknown: int = 0


class AuditForecastYearOut(BaseModel):
    """Год прогноза: показатель, поток и его приведённая стоимость."""

    year: int
    ebit: Decimal
    depreciation: Decimal
    capex: Decimal
    nwc_change: Decimal
    fcff: Decimal
    discount_factor: Decimal
    present_value: Decimal


class AuditBridgeItemOut(BaseModel):
    """Слагаемое моста EV → цена: подпись, знак и величина."""

    label: str
    amount: Decimal
    kind: str                            # add | subtract | total
    note: str = ""


class AuditValuationOut(BaseModel):
    """Оценка стоимости (SPEC, Прил. П).

    Непустой ``blockers`` означает, что оценка **не посчитана**, а не «стоит 0»:
    величины, для которой не хватает входных данных, не существует. Забалансовые
    обязательства из моста исключены намеренно (Л.1) и названы в ``warnings``.
    """

    enabled: bool = False
    blockers: list[str] = []
    base_code: str = "EBIT"
    base_ebit: Decimal = Decimal(0)
    wacc: Decimal = Decimal(0)
    terminal_growth: Decimal = Decimal(0)
    years: list[AuditForecastYearOut] = []
    pv_forecast: Decimal = Decimal(0)
    terminal_value: Optional[Decimal] = None
    pv_terminal: Optional[Decimal] = None
    enterprise_value: Optional[Decimal] = None
    terminal_share: Optional[Decimal] = None
    bridge: list[AuditBridgeItemOut] = []
    equity_value: Optional[Decimal] = None
    implied_multiple: Optional[Decimal] = None
    asking_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    sensitivity: list[list[Optional[Decimal]]] = []
    sensitivity_wacc: list[Decimal] = []
    sensitivity_growth: list[Decimal] = []
    equity_min: Optional[Decimal] = None
    equity_max: Optional[Decimal] = None
    warnings: list[str] = []
    not_computed: list[str] = []


class AuditHeadMetricOut(BaseModel):
    """Показатель шапки сводки. ``value=None`` — величина не считается, а не равна нулю."""

    key: str
    label: str
    value: Optional[Decimal] = None
    unit: str                            # money | ratio | grade
    note: str = ""
    tone: str = "neutral"                # ok | warn | risk | neutral
    text: str = ""                       # буквенное значение (качество прибыли)


class AuditSummaryOut(BaseModel):
    """Сводка дела и вердикт (SPEC, Прил. Н).

    Оценки сделки здесь нет намеренно: запрошенной цены в модели не существует, DCF не
    построен, бенчмарков нет. ``priced_total`` — оценённое влияние флагов, **не скидка
    к цене**. Всё, чего сводка не считает, перечислено в ``not_computed``.
    """

    state: str = "empty"                 # empty | ready
    verdict: str = "ok"                  # unreliable | risk | warning | ok
    headline: str = ""
    detail: str = ""
    coverage: Optional[Decimal] = None
    open_procedures: int = 0
    metrics: list[AuditHeadMetricOut] = []
    risk_flags: int = 0
    warning_flags: int = 0
    priced_total: Decimal = Decimal(0)
    unpriced: int = 0
    input_errors: int = 0
    # Оценка (Прил. П); None — оценки нет, и дисконта не существует.
    equity_value: Optional[Decimal] = None
    asking_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    not_computed: list[str] = []


class AuditProcedureOut(BaseModel):
    """Процедура чек-листа: что проверяется, кем и с каким итогом."""

    code: str
    group: str
    title: str
    source: str                          # system | analyst
    method: str                          # чем выполняется (или почему нужен человек)
    #: pass | finding | no_data — выводится из прогона; done | skipped | pending — отметка.
    status: str
    detail: str = ""
    findings: list[str] = []             # коды сработавших находок


class AuditProceduresOut(BaseModel):
    """Чек-лист целиком: итоги, охват и границы проверки (SPEC, Прил. М).

    ``coverage`` честен только вместе с ``limits``: «охват 70%» без перечня тех 30%
    читается как «почти всё проверено», а не как «треть не проверялась».
    """

    items: list[AuditProcedureOut] = []
    total: int = 0
    closed: int = 0
    passed: int = 0
    findings: int = 0
    no_data: int = 0
    done: int = 0
    skipped: int = 0
    pending: int = 0
    coverage: Optional[Decimal] = None   # None — каталога нет, делить не на что
    limits: list[str] = []


class AuditInputIssueOut(BaseModel):
    """Находка проверки ввода: что не так с данными и в каких периодах."""

    code: str
    severity: str                      # error | warning | info
    title: str
    detail: str
    periods: list[int] = []            # индексы периодов (пусто — вся модель)
    evidence: dict[str, Decimal] = {}


class AuditEliminationIn(BaseModel):
    """Внутригрупповые величины к исключению из свода (по периодам).

    Каждая вычитается парно по обе стороны баланса, поэтому «актив = пассив» сохраняется:
    задолженность — из дебиторки и кредиторки, выручка — из выручки и себестоимости,
    вложения — из внеоборотных активов и капитала, нереализованная прибыль — из запасов
    и капитала (плюс восстановление себестоимости в ОПУ).
    """

    receivables: list[Decimal] = []
    revenue: list[Decimal] = []
    investments: list[Decimal] = []
    unrealized_profit: list[Decimal] = []


class AuditConsolidateRequest(BaseModel):
    """Запрос консолидации: список субъектов группы + имя свода + исключения (v2)."""

    subject_ids: list[str] = Field(default_factory=list, min_length=1, max_length=50)
    name: str = "Группа предприятий"
    elimination: Optional[AuditEliminationIn] = None


class AuditConsolidateResponse(BaseModel):
    """Свод группы: анализ консолидированной отчётности + состав и оговорки."""

    analysis: AuditAnalysisOut
    members: list[str] = []            # имена вошедших субъектов
    periods_used: list[str] = []
    warnings: list[str] = []
    # Участники сохранённой группы, которых больше нет (субъект удалён). Свод считается по
    # оставшимся, но состав изменился — молчать об этом нельзя. Для разового свода пусто.
    missing_members: list[str] = []


# --- Сохранённые группы предприятий (Финанс-Аудит, v2) ---

class AuditGroupMember(BaseModel):
    """Участник сохранённой группы: ссылка на субъект + имя на момент сохранения.

    Имя — только «надгробие»: если субъект удалён, по нему называют выбывшего участника.
    У живого участника имя всегда берётся из самого субъекта (переименование не теряется).
    """

    subject_id: str
    name: str = Field(default="", max_length=255)


class AuditGroupModel(BaseModel):
    """Состав группы: участники + внутригрупповые обороты к исключению.

    Хранится именно состав, а не результат: свод пересчитывается по текущей отчётности
    участников при каждом анализе.
    """

    members: list[AuditGroupMember] = Field(default_factory=list, max_length=50)
    elimination: Optional[AuditEliminationIn] = None


class AuditGroupCreate(BaseModel):
    name: str = "Группа предприятий"
    model: AuditGroupModel = Field(default_factory=AuditGroupModel)


class AuditGroupUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[AuditGroupModel] = None


class AuditGroupSummary(BaseModel):
    """Метаданные группы: сколько участников сохранено и сколько из них ещё существует."""

    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    n_members: int = 0
    n_missing: int = 0


class AuditGroupOut(AuditGroupSummary):
    model: AuditGroupModel


def audit_analysis_response(result, opinion: str = "", issues=(),
                            flags=None, earnings=None, obligations=None,
                            procedures=None, summary=None,
                            valuation=None) -> "AuditAnalysisOut":
    """Собрать ответ анализа из ``audit_core.AuditResult`` (+ заключение, ввод, флаги)."""
    return AuditAnalysisOut(
        opinion=opinion,
        summary=AuditSummaryOut(
            state=summary.state if summary else "empty",
            verdict=summary.verdict if summary else "ok",
            headline=summary.headline if summary else "",
            detail=summary.detail if summary else "",
            coverage=summary.coverage if summary else None,
            open_procedures=summary.open_procedures if summary else 0,
            metrics=[AuditHeadMetricOut(key=m.key, label=m.label, value=m.value,
                                        unit=m.unit, note=m.note, tone=m.tone,
                                        text=m.text)
                     for m in (summary.metrics if summary else [])],
            risk_flags=summary.risk_flags if summary else 0,
            warning_flags=summary.warning_flags if summary else 0,
            priced_total=summary.priced_total if summary else Decimal(0),
            unpriced=summary.unpriced if summary else 0,
            input_errors=summary.input_errors if summary else 0,
            equity_value=summary.equity_value if summary else None,
            asking_price=summary.asking_price if summary else None,
            discount=summary.discount if summary else None,
            not_computed=list(summary.not_computed) if summary else [],
        ),
        valuation=AuditValuationOut(
            enabled=valuation.enabled if valuation else False,
            blockers=list(valuation.blockers) if valuation else [],
            base_code=valuation.base_code if valuation else "EBIT",
            base_ebit=valuation.base_ebit if valuation else Decimal(0),
            wacc=valuation.wacc if valuation else Decimal(0),
            terminal_growth=valuation.terminal_growth if valuation else Decimal(0),
            years=[AuditForecastYearOut(
                year=y.year, ebit=y.ebit, depreciation=y.depreciation, capex=y.capex,
                nwc_change=y.nwc_change, fcff=y.fcff,
                discount_factor=y.discount_factor, present_value=y.present_value)
                for y in (valuation.years if valuation else [])],
            pv_forecast=valuation.pv_forecast if valuation else Decimal(0),
            terminal_value=valuation.terminal_value if valuation else None,
            pv_terminal=valuation.pv_terminal if valuation else None,
            enterprise_value=valuation.enterprise_value if valuation else None,
            terminal_share=valuation.terminal_share if valuation else None,
            bridge=[AuditBridgeItemOut(label=b.label, amount=b.amount, kind=b.kind,
                                       note=b.note)
                    for b in (valuation.bridge if valuation else [])],
            equity_value=valuation.equity_value if valuation else None,
            implied_multiple=valuation.implied_multiple if valuation else None,
            asking_price=valuation.asking_price if valuation else None,
            discount=valuation.discount if valuation else None,
            sensitivity=[list(r) for r in (valuation.sensitivity if valuation else [])],
            sensitivity_wacc=list(valuation.sensitivity_wacc) if valuation else [],
            sensitivity_growth=list(valuation.sensitivity_growth) if valuation else [],
            equity_min=valuation.equity_min if valuation else None,
            equity_max=valuation.equity_max if valuation else None,
            warnings=list(valuation.warnings) if valuation else [],
            not_computed=list(valuation.not_computed) if valuation else [],
        ),
        procedures=AuditProceduresOut(
            items=[AuditProcedureOut(
                code=i.code, group=i.group, title=i.title, source=i.source,
                method=i.method, status=i.status, detail=i.detail,
                findings=list(i.findings),
            ) for i in (procedures.items if procedures else [])],
            total=procedures.total if procedures else 0,
            closed=procedures.closed if procedures else 0,
            passed=procedures.passed if procedures else 0,
            findings=procedures.findings if procedures else 0,
            no_data=procedures.no_data if procedures else 0,
            done=procedures.done if procedures else 0,
            skipped=procedures.skipped if procedures else 0,
            pending=procedures.pending if procedures else 0,
            coverage=procedures.coverage if procedures else None,
            limits=list(procedures.limits) if procedures else [],
        ),
        obligations=AuditObligationsOut(
            rows=[AuditObligationRowOut(
                creditor=r.creditor, contract=r.contract, kind=r.kind,
                kind_label=r.kind_label, off_balance=r.off_balance, amount=r.amount,
                rate=r.rate, maturity=r.maturity, on_demand=r.on_demand,
                collateral=r.collateral, pledged_amount=r.pledged_amount,
                covenant=r.covenant, covenant_status=r.covenant_status,
                covenant_note=r.covenant_note,
            ) for r in (obligations.rows if obligations else [])],
            balance_debt=obligations.balance_debt if obligations else Decimal(0),
            off_balance=obligations.off_balance if obligations else Decimal(0),
            reported_debt=obligations.reported_debt if obligations else Decimal(0),
            discrepancy=obligations.discrepancy if obligations else Decimal(0),
            reconciled=obligations.reconciled if obligations else True,
            buckets=[AuditMaturityBucketOut(label=b.label, amount=b.amount, kind=b.kind)
                     for b in (obligations.buckets if obligations else [])],
            pledged_total=obligations.pledged_total if obligations else Decimal(0),
            free_assets=obligations.free_assets if obligations else None,
            pledged_share=obligations.pledged_share if obligations else None,
            covenants_breached=obligations.covenants_breached if obligations else 0,
            covenants_unknown=obligations.covenants_unknown if obligations else 0,
        ),
        earnings=AuditEarningsOut(
            base_code=earnings.base_code if earnings else "EBIT",
            reported=list(earnings.reported) if earnings else [],
            normalized=list(earnings.normalized) if earnings else [],
            adjustments=[AuditAdjustmentOut(label=a.label, kind=a.kind,
                                            kind_label=a.kind_label,
                                            amounts=list(a.amounts), total=a.total)
                         for a in (earnings.adjustments if earnings else [])],
            grade=earnings.grade if earnings else None,
            grade_note=earnings.grade_note if earnings else "",
            deviation=earnings.deviation if earnings else None,
        ),
        flags=AuditFlagsOut(
            flags=[AuditFlagOut(code=f.code, severity=f.severity, title=f.title,
                                detail=f.detail, periods=list(f.periods),
                                impact=f.impact, evidence=dict(f.evidence))
                   for f in (flags.flags if flags else [])],
            priced_total=flags.priced_total if flags else Decimal(0),
            unpriced=flags.unpriced if flags else 0,
        ),
        input_issues=[AuditInputIssueOut(code=i.code, severity=i.severity, title=i.title,
                                         detail=i.detail, periods=list(i.periods),
                                         evidence=dict(i.evidence)) for i in issues],
        n=result.n,
        periods=list(result.periods),
        balance=[AuditLineOut(code=ln.code, label=ln.label, values=list(ln.values),
                              subtotal=ln.subtotal) for ln in result.balance],
        income=[AuditLineOut(code=ln.code, label=ln.label, values=list(ln.values),
                             subtotal=ln.subtotal) for ln in result.income],
        horizontal=[AuditTrendOut(code=t.code, label=t.label, delta=list(t.delta),
                                  rate=list(t.rate)) for t in result.horizontal],
        vertical=[AuditShareOut(code=s.code, label=s.label, share=list(s.share))
                  for s in result.vertical],
        ratios={g: {k: list(v) for k, v in series.items()}
                for g, series in result.ratios.items()},
        balance_gap=list(result.balance_gap),
        balanced=result.balanced,
        revalued=result.revalued,
        user_metrics=[AuditUserMetricOut(name=u.name, values=list(u.values), error=u.error)
                      for u in result.user_metrics],
        diagnostics=(AuditDiagnosticsOut(
            light=result.diagnostics.light,
            summary=result.diagnostics.summary,
            scores=[AuditScoreOut(id=s.id, name=s.name, values=list(s.values),
                                  zones=list(s.zones), note=s.note)
                    for s in result.diagnostics.scores],
            assessments=[AuditAssessmentOut(group=a.group, name=a.name, status=list(a.status))
                         for a in result.diagnostics.assessments],
        ) if result.diagnostics is not None else None),
        warnings=list(result.warnings),
    )
