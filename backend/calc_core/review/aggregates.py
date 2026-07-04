"""Агрегаты над результатом/моделью для правил ревью (коды строк — из reports/lines.py)."""
from __future__ import annotations

from decimal import Decimal

from ..models import ProjectModel
from ..money import ZERO
from ..reports.result import CalcResult
from ..reports.statements import Statement


def series(stmt: Statement, code: str) -> list[Decimal]:
    """Ряд строки по коду (пустой список, если строки нет)."""
    return stmt.lines.get(code, [])


def total(stmt: Statement, code: str) -> Decimal:
    """Сумма ряда строки за весь горизонт."""
    return sum(series(stmt, code), ZERO)


def total_net_revenue(result: CalcResult) -> Decimal:
    """Чистый объём продаж за горизонт (I4)."""
    return total(result.income, "I4")


def total_gross_profit(result: CalcResult) -> Decimal:
    """Валовая прибыль за горизонт (I8)."""
    return total(result.income, "I8")


def gross_margin(result: CalcResult) -> Decimal | None:
    """Валовая маржа = ΣI8 / ΣI4 (None при нулевой выручке)."""
    rev = total_net_revenue(result)
    return (total_gross_profit(result) / rev) if rev != 0 else None


def interest_total(result: CalcResult) -> Decimal:
    """Проценты по кредитам за горизонт (I18)."""
    return total(result.income, "I18")


def ebit_total(result: CalcResult) -> Decimal:
    """EBIT ≈ прибыль до налога (I23) + проценты (I18) — до процентов и налога."""
    return total(result.income, "I23") + interest_total(result)


def per_product_revenue(model: ProjectModel) -> dict[str, Decimal]:
    """Выручка по продукту из модели: Σ объём×цена (валютные строки — по курсу FX[t])."""
    fx = model.environment.fx_rate
    fx_open = model.environment.fx_open
    out: dict[str, Decimal] = {}
    for line in model.operating_plan.sales:
        m = min(len(line.volume), len(line.price))
        rev = ZERO
        for t in range(m):
            rate = (fx[t] if t < len(fx) else fx_open) if line.foreign else Decimal(1)
            rev += line.volume[t] * line.price[t] * rate
        out[line.product_id] = out.get(line.product_id, ZERO) + rev
    return out
