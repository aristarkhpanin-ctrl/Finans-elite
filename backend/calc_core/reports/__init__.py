"""Структуры результатов расчёта."""
from __future__ import annotations

from .breakeven import BreakEven, compute_break_even
from .ratios import FinancialRatios, compute_ratios
from .result import CalcResult, InvestmentMetrics
from .statements import (
    Statement,
    build_balance,
    build_cashflow,
    build_income,
    build_profit_use,
)
from .valuation import BusinessValuation, compute_valuation

__all__ = [
    "Statement",
    "CalcResult",
    "InvestmentMetrics",
    "FinancialRatios",
    "compute_ratios",
    "BreakEven",
    "compute_break_even",
    "BusinessValuation",
    "compute_valuation",
    "build_income",
    "build_cashflow",
    "build_balance",
    "build_profit_use",
]
