"""Актуализация Кэш-фло (план-факт, SPEC §4.9).

Фактические значения листовых строк Кэш-фло подставляются для прошедших периодов
(``t <= actual_until``), субитоги и сальдо пересчитываются. Рассогласование =
актуализированный − план по каждой строке.
"""
from __future__ import annotations

from decimal import Decimal

from ..money import D
from .lines import CASHFLOW_LINES
from .statements import Statement, build_cashflow

# Вычисляемые (не листовые) строки Кэш-фло — их нельзя задавать как факт.
_COMPUTED = {"C4", "C7", "C13", "C20", "C27", "C29"}
LEAF_CODES = [code for code, _ in CASHFLOW_LINES if code not in _COMPUTED]


def actualize_cashflow(plan: Statement, actual_until: int,
                       actuals: dict[str, list[Decimal]], n: int):
    """Вернуть ``(actualized, variance)`` — актуализированный Кэш-фло и рассогласование."""
    leaves = {code: list(plan[code]) for code in LEAF_CODES}
    for code, values in actuals.items():
        if code not in leaves:
            raise ValueError(f"Строка {code} не является фактически задаваемой строкой Кэш-фло")
        for t, v in enumerate(values):
            if 0 <= t <= actual_until and t < n:
                leaves[code][t] = D(v)

    actualized = build_cashflow(leaves, n)

    variance = Statement(CASHFLOW_LINES, n)
    for code in plan.order:
        variance[code] = [actualized[code][t] - plan[code][t] for t in range(n)]
    return actualized, variance
