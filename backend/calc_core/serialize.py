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
        "mirr_annual": _ratio(m.mirr_annual),
        "arr_annual": _ratio(m.arr_annual),
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
        "dividend_value": _money(v.dividend_value),
        "earnings_multiple_value": _money(v.earnings_multiple_value),
        "liquidation_value": _money(v.liquidation_value),
    }


def budget_to_dict(budget) -> dict[str, object]:
    return {
        "stages": [
            {"id": s.id, "name": s.name, "kind": s.kind, "start_month": s.start_month,
             "finish_month": s.finish_month, "cost": _money(s.cost),
             "actual_start_month": s.actual_start_month,
             "actual_finish_month": s.actual_finish_month,
             "actual_cost": _money(s.actual_cost),
             "cost_variance": _money(s.cost_variance),
             "schedule_variance_months": s.schedule_variance_months}
            for s in budget.stages
        ],
        "monthly": [_money(v) for v in budget.monthly],
        "total": _money(budget.total),
        "actual_total": _money(budget.actual_total),
    }


def product_margins_to_dict(pm) -> dict[str, object]:
    return {
        "products": [
            {"product_id": p.product_id, "name": p.name, "revenue": _money(p.revenue),
             "bom_cost": _money(p.bom_cost), "piece_wages": _money(p.piece_wages),
             "margin": _money(p.margin), "margin_share": _ratio(p.margin_share)}
            for p in pm.products
        ],
        "unallocated_direct": _money(pm.unallocated_direct),
    }


def participants_to_dict(items) -> list[dict[str, object]]:
    return [
        {"id": p.id, "name": p.name, "kind": p.kind,
         "invested": _money(p.invested), "withdrawn": _money(p.withdrawn),
         "npv": _money(p.npv), "irr_annual": _ratio(p.irr_annual),
         "terminal_value": _money(p.terminal_value),
         "npv_with_terminal": _money(p.npv_with_terminal),
         "irr_with_terminal_annual": _ratio(p.irr_with_terminal_annual),
         "flow": [_money(v) for v in p.flow]}
        for p in items
    ]


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
    if result.budget.stages:
        snapshot["budget"] = budget_to_dict(result.budget)
    if result.product_margins.products:
        snapshot["product_margins"] = product_margins_to_dict(result.product_margins)
    if result.participants:
        snapshot["participants"] = participants_to_dict(result.participants)
    if result.user_tables:
        snapshot["user_tables"] = [
            {"id": t.id, "name": t.name,
             "rows": [{"name": r.name, "values": [_money(v) for v in r.values],
                       "error": r.error} for r in t.rows]}
            for t in result.user_tables
        ]
    if result.metrics_foreign is not None:
        snapshot["metrics_foreign"] = metrics_to_dict(result.metrics_foreign)
    if result.actualized_cashflow is not None:
        snapshot["actualized_cashflow"] = statement_to_dict(result.actualized_cashflow)
    if result.cashflow_variance is not None:
        snapshot["cashflow_variance"] = statement_to_dict(result.cashflow_variance)
    return snapshot
