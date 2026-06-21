"""Анализ безубыточности (7.2; SPEC §20).

Маржинальный подход (по периодам):
- переменные издержки = прямые издержки (себестоимость, I7);
- постоянные издержки = налог на имущество (I9) + суммарные постоянные (I16) +
  амортизация (I17) + проценты (I18);
- маржинальный доход = чистый объём продаж − переменные = валовая прибыль (I8);
- выручка безубыточности = постоянные / (I8 / I4) = постоянные · I4 / I8;
- запас финансовой прочности = (I4 − выручка безубыточности) / I4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .statements import Statement


@dataclass
class BreakEven:
    break_even_revenue: list[Optional[Decimal]] = field(default_factory=list)  # выручка безубыточности
    margin_of_safety: list[Optional[Decimal]] = field(default_factory=list)    # запас прочности (доля)


def compute_break_even(income: Statement, n: int) -> BreakEven:
    be = BreakEven()
    for t in range(n):
        i4 = income["I4"][t]
        i8 = income["I8"][t]  # маржинальный доход = I4 − I7
        fixed = income["I9"][t] + income["I16"][t] + income["I17"][t] + income["I18"][t]
        if i4 <= 0 or i8 <= 0:
            be.break_even_revenue.append(None)
            be.margin_of_safety.append(None)
            continue
        bep = fixed * i4 / i8
        be.break_even_revenue.append(bep)
        be.margin_of_safety.append((i4 - bep) / i4)
    return be
