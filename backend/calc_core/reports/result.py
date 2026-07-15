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
    """Строка сметы по этапу календарного плана (группы — со свёрнутой стоимостью)."""

    id: str
    name: str
    kind: str            # expense | asset | production
    start_month: int
    finish_month: int
    cost: Decimal


@dataclass
class Budget:
    """Бюджет проекта по этапам: смета (строки) + помесячный график + итог."""

    stages: list[StageBudget] = field(default_factory=list)
    monthly: list[Decimal] = field(default_factory=list)  # Σ стоимости этапов по месяцам (начисление)
    total: Decimal = Decimal(0)


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
class InvestmentMetrics:
    """Показатели эффективности инвестиций (SPEC §17)."""

    npv: Decimal = Decimal(0)
    irr_annual: Decimal | None = None
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
        discounted_payback_months,
        investment_graph,
        irr_annual,
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
    ratios: FinancialRatios = field(default_factory=FinancialRatios)
    break_even: BreakEven = field(default_factory=BreakEven)
    valuation: BusinessValuation = field(default_factory=BusinessValuation)
    # Бюджет по этапам (календарный план); пустой, если этапов нет.
    budget: Budget = field(default_factory=Budget)
    # Маржа по продуктам (рецептуры/BOM); пустая, если рецептур нет.
    product_margins: ProductMargins = field(default_factory=ProductMargins)
    # Актуализация (план-факт): заполняются при наличии фактических данных.
    actualized_cashflow: Optional[Statement] = None
    cashflow_variance: Optional[Statement] = None
    warnings: list[str] = field(default_factory=list)
