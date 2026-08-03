"""Результат расчёта проекта."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .breakeven import BreakEven
from .ratios import FinancialRatios
from .statements import Statement
from .valuation import BusinessValuation


@dataclass
class StageBudget:
    """Строка сметы по этапу календарного плана (группы — со свёрнутой стоимостью).

    Факт-поля (план-факт, gap 4.6) — ``None``, если этап не актуализирован; отклонения
    считаются от плана (``cost_variance`` = факт − план стоимости; ``schedule_variance_months``
    = факт-финиш − план-финиш).
    """

    id: str
    name: str
    kind: str            # expense | asset | production
    start_month: int
    finish_month: int
    cost: Decimal
    actual_start_month: Optional[int] = None
    actual_finish_month: Optional[int] = None
    actual_cost: Optional[Decimal] = None
    cost_variance: Optional[Decimal] = None
    schedule_variance_months: Optional[int] = None
    #: Освоение (начисление стоимости) по месяцам — то, что этап «съедает» по графику работ.
    monthly: list[Decimal] = field(default_factory=list)
    #: Оплата по месяцам — то же освоение, сдвинутое на отсрочку платежа ресурсов.
    #: Расхождение с ``monthly`` и есть кредиторка по этапу (см. ``Budget.payables``).
    monthly_cash: list[Decimal] = field(default_factory=list)
    #: Трактовка стоимости в отчётах: expense (издержка периода, I21) | deferred (РБП, B15)
    #: | asset (капвложение, C14→B14) | none (этап стоимости не несёт). У групп — от потомков,
    #: если она у них одна; при смешении — "mixed" (свод не приписывает группе чужую трактовку).
    treatment: str = "none"


@dataclass
class Budget:
    """Бюджет проекта по этапам: смета (строки) + помесячные графики + итоги.

    Финансовый разрез сметы: **освоение и оплата — разные ряды**. Стоимость начисляется по
    графику работ (``monthly``), а платится с отсрочкой ресурсов (``monthly_cash``); разрыв
    между накопленными рядами — неоплаченные обязательства (``payables``, тот же ряд, что
    уходит в кредиторку B23). Итоги по трактовке показывают, куда стоимость попадёт в
    отчётах: в издержки периода, в расходы будущих периодов или в основные средства.
    """

    stages: list[StageBudget] = field(default_factory=list)
    monthly: list[Decimal] = field(default_factory=list)  # Σ стоимости этапов по месяцам (начисление)
    total: Decimal = Decimal(0)
    # Σ фактических стоимостей листьев (None, если факта нет) — план-факт итог.
    actual_total: Optional[Decimal] = None
    #: Платежи по месяцам (освоение со сдвигом на отсрочку ресурсов).
    monthly_cash: list[Decimal] = field(default_factory=list)
    #: Накопленное освоение и накопленная оплата (S-кривые бюджетного контроля).
    cumulative: list[Decimal] = field(default_factory=list)
    cumulative_cash: list[Decimal] = field(default_factory=list)
    #: Начислено − оплачено на конец месяца: обязательства перед подрядчиками.
    payables: list[Decimal] = field(default_factory=list)
    #: Разбивка сметы по трактовке (Σ = ``total``): издержки периода, РБП, капвложения.
    expense_total: Decimal = Decimal(0)
    deferred_total: Decimal = Decimal(0)
    asset_total: Decimal = Decimal(0)


@dataclass
class ProductMargin:
    """Маржа продукта по рецептуре (аналитика; отчётные формы не затрагивает).

    ``bom_cost`` — BOM-себестоимость проданного объёма в ценах месяца продажи;
    ``margin_share`` — доля маржи в выручке (None при нулевой выручке).
    """

    product_id: str
    name: str
    revenue: Decimal
    bom_cost: Decimal
    piece_wages: Decimal
    margin: Decimal
    margin_share: Optional[Decimal]


@dataclass
class ProductMargins:
    """Маржа по продуктам с рецептурой + нераспределённые (суммовые) прямые издержки."""

    products: list[ProductMargin] = field(default_factory=list)
    unallocated_direct: Decimal = Decimal(0)


@dataclass
class DivisionMargin:
    """Маржа подразделения (gap 4.5): свёртка маржи продуктов бизнес-единицы.

    Аналитика поверх ``product_margins`` — суммирует продукты с рецептурой, отнесённые к
    подразделению. Продукты без рецептуры/без подразделения сюда не входят (как и в маржу
    продуктов — без фейковой аллокации). ``product_count`` — число сведённых продуктов.
    """

    division_id: str
    name: str
    revenue: Decimal
    bom_cost: Decimal
    piece_wages: Decimal
    margin: Decimal
    margin_share: Optional[Decimal]
    product_count: int


@dataclass
class ParticipantFlow:
    """Доходы участника финансирования (SPEC §17): поток, вложено/получено, NPV/IRR.

    Акционеры дополнительно получают вариант «с терминальной стоимостью» — условным
    изъятием собственного капитала (B33) в последнем месяце (классический equity-IRR).
    """

    id: str
    name: str
    kind: str                                   # "equity" | "lender"
    flow: list[Decimal]                         # чистый поток: − вложения, + изъятия
    invested: Decimal
    withdrawn: Decimal
    npv: Decimal
    irr_annual: Optional[Decimal]
    terminal_value: Optional[Decimal] = None            # только акционеры: B33 на конец
    npv_with_terminal: Optional[Decimal] = None
    irr_with_terminal_annual: Optional[Decimal] = None


@dataclass
class LineDetailItem:
    """Слагаемое строки отчёта (drill-down): источник и его помесячный ряд."""

    name: str
    values: list[Decimal]


@dataclass
class LineDetail:
    """Детализация строки отчёта по источникам (пакет №6, Q4).

    Слагаемые сохранены конвейером в момент расчёта (не перерасчёт):
    Σ ``items`` = строка отчёта точно (Decimal). В golden-снимок не входит (Q5).
    """

    code: str
    items: list[LineDetailItem] = field(default_factory=list)


@dataclass
class UserRowResult:
    """Вычисленная строка таблицы пользователя: ряд значений либо ошибка формулы."""

    name: str
    values: list[Decimal]
    error: Optional[str] = None


@dataclass
class UserTableResult:
    """Вычисленная таблица пользователя."""

    id: str
    name: str
    rows: list[UserRowResult] = field(default_factory=list)


@dataclass
class InvestmentMetrics:
    """Показатели эффективности инвестиций (SPEC §17)."""

    npv: Decimal = Decimal(0)
    irr_annual: Decimal | None = None
    mirr_annual: Decimal | None = None  # модифицированная IRR (реинвестиции по ставке диск.)
    arr_annual: Decimal | None = None   # средняя норма рентабельности
    pi: Decimal | None = None
    pb_months: int | None = None       # срок окупаемости
    dpb_months: int | None = None      # дисконтированный срок окупаемости
    pv_investments: Decimal | None = None      # приведённая потребность в капитале
    peak_financing_need: Decimal | None = None  # пиковая потребность в финансировании


def build_investment_metrics(net_flow, monthly_rate: Decimal) -> InvestmentMetrics:
    """Собрать показатели эффективности из потока до финансирования (SPEC §17/§22.4).

    Единая точка расчёта (используется и движком, и Integrator-ом): NPV/IRR/PB/DPB — на
    чистом потоке; PI и потребность в капитале — на графике инвестиций.
    """
    from ..metrics import (
        arr_annual,
        discounted_payback_months,
        investment_graph,
        irr_annual,
        mirr_annual,
        npv,
        payback_months,
        profitability_index,
    )
    from ..series import total

    npv_value = npv(net_flow, monthly_rate)
    inv = investment_graph(net_flow)
    pv_invest = npv(inv, monthly_rate)
    return InvestmentMetrics(
        npv=npv_value,
        irr_annual=irr_annual(net_flow),
        # Ставка финансирования и реинвестиций = ставке дисконтирования (дефолт PE-практики).
        mirr_annual=mirr_annual(net_flow, monthly_rate, monthly_rate),
        arr_annual=arr_annual(net_flow),
        pi=profitability_index(npv_value, pv_invest),
        pb_months=payback_months(net_flow),
        dpb_months=discounted_payback_months(net_flow, monthly_rate),
        pv_investments=pv_invest,
        peak_financing_need=total(inv),
    )


@dataclass
class CalcResult:
    """Полный результат расчёта."""

    engine_version: str
    n: int
    income: Statement
    cashflow: Statement
    balance: Statement
    profit_use: Statement
    metrics: InvestmentMetrics = field(default_factory=InvestmentMetrics)
    # Показатели во второй валюте (SPEC §17); None, если ставка дисконтирования по валюте
    # не задана (поток пересчитан по курсу fx_rate, дисконт — своей ставкой валюты).
    metrics_foreign: Optional[InvestmentMetrics] = None
    ratios: FinancialRatios = field(default_factory=FinancialRatios)
    break_even: BreakEven = field(default_factory=BreakEven)
    valuation: BusinessValuation = field(default_factory=BusinessValuation)
    # Бюджет по этапам (календарный план); пустой, если этапов нет.
    budget: Budget = field(default_factory=Budget)
    # Маржа по продуктам (рецептуры/BOM); пустая, если рецептур нет.
    product_margins: ProductMargins = field(default_factory=ProductMargins)
    # Маржа по подразделениям (свёртка маржи продуктов); пусто без подразделений.
    division_margins: list[DivisionMargin] = field(default_factory=list)
    # Таблицы пользователя (строки-формулы); пустые, если таблиц нет.
    user_tables: list[UserTableResult] = field(default_factory=list)
    # Детализация ключевых строк отчётов (drill-down); не входит в golden-снимок.
    details: list[LineDetail] = field(default_factory=list)
    # Доходы участников финансирования (акционеры, кредиторы); пусто без финансирования.
    participants: list[ParticipantFlow] = field(default_factory=list)
    # Актуализация (план-факт): заполняются при наличии фактических данных.
    actualized_cashflow: Optional[Statement] = None
    cashflow_variance: Optional[Statement] = None
    warnings: list[str] = field(default_factory=list)
