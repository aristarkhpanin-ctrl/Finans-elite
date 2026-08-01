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


class BudgetOut(BaseModel):
    """Смета по этапам календарного плана + помесячный график и итог."""

    stages: list[StageBudgetOut] = []
    monthly: list[Decimal] = []
    total: Decimal = Decimal(0)
    actual_total: Optional[Decimal] = None


def budget_response(budget) -> "BudgetOut":
    """Собрать смету-ответ из ``calc_core.reports.result.Budget``."""
    return BudgetOut(
        stages=[StageBudgetOut(
            id=s.id, name=s.name, kind=s.kind, start_month=s.start_month,
            finish_month=s.finish_month, cost=s.cost,
            actual_start_month=s.actual_start_month, actual_finish_month=s.actual_finish_month,
            actual_cost=s.actual_cost, cost_variance=s.cost_variance,
            schedule_variance_months=s.schedule_variance_months)
            for s in budget.stages],
        monthly=list(budget.monthly),
        total=budget.total,
        actual_total=budget.actual_total,
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


class MemberOut(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str


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


# --- Тарифы и подписка (биллинг, 6.5) ---

class PlanOut(BaseModel):
    code: str
    name: str
    price_rub: int
    max_projects: Optional[int] = None
    max_members: Optional[int] = None


class SubscriptionOut(BaseModel):
    plan_code: str
    plan_name: str
    status: str
    current_period_end: Optional[datetime] = None
    max_projects: Optional[int] = None
    max_members: Optional[int] = None
    used_projects: int
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


def audit_analysis_response(result, opinion: str = "") -> "AuditAnalysisOut":
    """Собрать ответ анализа из ``audit_core.AuditResult`` (+ текст заключения)."""
    return AuditAnalysisOut(
        opinion=opinion,
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
