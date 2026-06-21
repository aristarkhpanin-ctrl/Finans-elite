"""Integrator (9.2): консолидация нескольких независимых проектов в группу.

Сводная отчётность = построчная сумма отчётов проектов (одинаковой длительности).
Балансовый инвариант сохраняется: сумма сходящихся балансов сходится. Групповые
показатели считаются на консолидированном денежном потоке.
"""
from __future__ import annotations

from decimal import Decimal

from .metrics import annual_to_monthly
from .models import ProjectModel
from .money import D
from .reports import compute_break_even, compute_ratios
from .reports.lines import (
    BALANCE_LINES,
    CASHFLOW_LINES,
    INCOME_LINES,
    PROFIT_USE_LINES,
)
from .reports.result import CalcResult, build_investment_metrics
from .reports.statements import Statement, opening_balance
from .series import add
from .version import ENGINE_VERSION


def _sum_statements(statements: list[Statement], catalog, n: int) -> Statement:
    out = Statement(catalog, n)
    for code, _ in catalog:
        out[code] = [sum((st[code][t] for st in statements), D(0)) for t in range(n)]
    return out


def consolidate(models: list[ProjectModel],
                group_discount_rate: Decimal = Decimal("0.15")) -> CalcResult:
    """Консолидировать проекты в группу и вернуть сводный результат."""
    from .engine import run  # локальный импорт (избегаем цикла)

    if not models:
        raise ValueError("Нужен хотя бы один проект")
    n = models[0].n
    for m in models:
        if m.n != n:
            raise ValueError("Проекты должны иметь одинаковую длительность")

    results = [run(m) for m in models]
    income = _sum_statements([r.income for r in results], INCOME_LINES, n)
    cashflow = _sum_statements([r.cashflow for r in results], CASHFLOW_LINES, n)
    balance = _sum_statements([r.balance for r in results], BALANCE_LINES, n)
    profit_use = _sum_statements([r.profit_use for r in results], PROFIT_USE_LINES, n)

    net_flow = add(cashflow["C13"], cashflow["C20"])
    r_m = annual_to_monthly(group_discount_rate)
    metrics = build_investment_metrics(net_flow, r_m)
    # Стартовый баланс группы = сумма стартовых балансов проектов (для средних в коэф-тах).
    sbs = [m.company.starting_balance for m in models]
    opening = opening_balance(
        sum((sb.cash for sb in sbs), D(0)),
        sum((sb.fixed_assets_net for sb in sbs), D(0)),
        sum((sb.debt for sb in sbs), D(0)),
        sum((sb.paid_in_capital for sb in sbs), D(0)),
        sum((sb.retained_earnings for sb in sbs), D(0)),
        sum((m.company.starting_balance.foreign_monetary * m.environment.fx_open
             for m in models), D(0)),
    )
    # Число акций по группе не определено → инвестиционные «на акцию» = None.
    ratios = compute_ratios(income, cashflow, balance, profit_use, D(0), n, opening)
    break_even = compute_break_even(income, n)

    return CalcResult(
        engine_version=ENGINE_VERSION,
        n=n,
        income=income,
        cashflow=cashflow,
        balance=balance,
        profit_use=profit_use,
        metrics=metrics,
        ratios=ratios,
        break_even=break_even,
    )
