"""Результат расчёта проекта."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from typing import Optional

from .breakeven import BreakEven
from .ratios import FinancialRatios
from .statements import Statement


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
    # Актуализация (план-факт): заполняются при наличии фактических данных.
    actualized_cashflow: Optional[Statement] = None
    cashflow_variance: Optional[Statement] = None
    warnings: list[str] = field(default_factory=list)
