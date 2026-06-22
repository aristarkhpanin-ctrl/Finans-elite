"""Канонизация результата расчёта в простой словарь (JSON-совместимый).

Используется для:
- **golden-master** тестов (см. ``tests/test_golden.py``): стабильный, читаемый при
  ревью снимок всех чисел расчёта;
- единого представления результата (отчёты/показатели/коэффициенты) вне зависимости
  от транспорта.

`Decimal` сериализуется в строку **фиксированной точности**: денежные суммы — до копеек
(2 знака), коэффициенты/ставки — до 6 знаков. Это делает снимки стабильными между
платформами и устойчивыми к дрейфу в последних разрядах, а диффы — читаемыми.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .money import D, quantize
from .reports.breakeven import BreakEven
from .reports.ratios import FinancialRatios
from .reports.result import CalcResult, InvestmentMetrics
from .reports.statements import Statement
from .reports.valuation import BusinessValuation

#: Точность денежных строк (копейки) и коэффициентов/ставок.
MONEY_PLACES = 2
RATIO_PLACES = 6

_RATIO_GROUPS = ("liquidity", "activity", "gearing", "profitability", "investment")


def _money(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return str(quantize(D(value), MONEY_PLACES))


def _ratio(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return str(quantize(D(value), RATIO_PLACES))


def statement_to_dict(stmt: Statement, places: int = MONEY_PLACES) -> dict[str, list[str]]:
    """Отчёт → {код строки: [значения по месяцам как строки]} в порядке каталога."""
    return {
        code: [str(quantize(D(v), places)) for v in stmt[code]]
        for code in stmt.order
    }


def metrics_to_dict(m: InvestmentMetrics) -> dict[str, object]:
    return {
        "npv": _money(m.npv),
        "irr_annual": _ratio(m.irr_annual),
        "pi": _ratio(m.pi),
        "pb_months": m.pb_months,
        "dpb_months": m.dpb_months,
        "pv_investments": _money(m.pv_investments),
        "peak_financing_need": _money(m.peak_financing_need),
    }


def ratios_to_dict(r: FinancialRatios) -> dict[str, dict[str, list[Optional[str]]]]:
    out: dict[str, dict[str, list[Optional[str]]]] = {}
    for group in _RATIO_GROUPS:
        series_by_key: dict[str, list[Optional[Decimal]]] = getattr(r, group)
        out[group] = {
            key: [_ratio(v) for v in series]
            for key, series in series_by_key.items()
        }
    return out


def break_even_to_dict(be: BreakEven) -> dict[str, list[Optional[str]]]:
    return {
        "break_even_revenue": [_money(v) for v in be.break_even_revenue],
        "margin_of_safety": [_ratio(v) for v in be.margin_of_safety],
    }


def valuation_to_dict(v: BusinessValuation) -> dict[str, Optional[str]]:
    return {
        "net_assets": _money(v.net_assets),
        "gordon_value": _money(v.gordon_value),
    }


def result_to_dict(result: CalcResult) -> dict[str, object]:
    """Полный канонический снимок результата расчёта (для golden-master и сравнения)."""
    snapshot: dict[str, object] = {
        "engine_version": result.engine_version,
        "n": result.n,
        "income": statement_to_dict(result.income),
        "cashflow": statement_to_dict(result.cashflow),
        "balance": statement_to_dict(result.balance),
        "profit_use": statement_to_dict(result.profit_use),
        "metrics": metrics_to_dict(result.metrics),
        "ratios": ratios_to_dict(result.ratios),
        "break_even": break_even_to_dict(result.break_even),
        "valuation": valuation_to_dict(result.valuation),
        "warnings": list(result.warnings),
    }
    if result.actualized_cashflow is not None:
        snapshot["actualized_cashflow"] = statement_to_dict(result.actualized_cashflow)
    if result.cashflow_variance is not None:
        snapshot["cashflow_variance"] = statement_to_dict(result.cashflow_variance)
    return snapshot
