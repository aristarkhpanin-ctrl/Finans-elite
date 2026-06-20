"""Структуры результатов расчёта."""
from __future__ import annotations

from .result import CalcResult, InvestmentMetrics
from .statements import (
    Statement,
    build_balance,
    build_cashflow,
    build_income,
    build_profit_use,
)

__all__ = [
    "Statement",
    "CalcResult",
    "InvestmentMetrics",
    "build_income",
    "build_cashflow",
    "build_balance",
    "build_profit_use",
]
