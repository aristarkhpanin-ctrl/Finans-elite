"""Результат расчёта проекта."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

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
    warnings: list[str] = field(default_factory=list)
