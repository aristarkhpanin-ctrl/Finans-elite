"""Помесячные временные ряды (векторы ``Decimal``).

Ядро работает над рядами длины ``N`` месяцев (см. SPEC §2). Чтобы сохранить точность,
ряд — это обычный ``list[Decimal]``, а не ``numpy``-массив (NumPy резервируется под
Монте-Карло). Здесь — минимальный набор операций над рядами.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Sequence

from .money import D, ZERO

Series = list  # семантический псевдоним: list[Decimal]


def zeros(n: int) -> list[Decimal]:
    """Ряд из ``n`` нулей."""
    return [ZERO for _ in range(n)]


def const(value, n: int) -> list[Decimal]:
    """Постоянный ряд длины ``n``."""
    v = D(value)
    return [v for _ in range(n)]


def from_list(values: Iterable, n: int) -> list[Decimal]:
    """Построить ряд длины ``n`` из значений, дополняя нулями/обрезая."""
    out = zeros(n)
    for i, v in enumerate(values):
        if i >= n:
            break
        out[i] = D(v)
    return out


def add(*series: Sequence[Decimal]) -> list[Decimal]:
    """Поэлементная сумма рядов одинаковой длины."""
    if not series:
        return []
    n = len(series[0])
    out = zeros(n)
    for s in series:
        _check_len(s, n)
        for i in range(n):
            out[i] += s[i]
    return out


def sub(a: Sequence[Decimal], b: Sequence[Decimal]) -> list[Decimal]:
    """Поэлементная разность ``a - b``."""
    _check_len(b, len(a))
    return [a[i] - b[i] for i in range(len(a))]


def neg(a: Sequence[Decimal]) -> list[Decimal]:
    """Поэлементное отрицание."""
    return [-x for x in a]


def scale(a: Sequence[Decimal], factor) -> list[Decimal]:
    """Умножить ряд на скаляр."""
    f = D(factor)
    return [x * f for x in a]


def cumulative(a: Sequence[Decimal]) -> list[Decimal]:
    """Накопленная сумма (нарастающим итогом)."""
    out: list[Decimal] = []
    running = ZERO
    for x in a:
        running += x
        out.append(running)
    return out


def total(a: Sequence[Decimal]) -> Decimal:
    """Сумма всех элементов ряда."""
    s = ZERO
    for x in a:
        s += x
    return s


def _check_len(s: Sequence[Decimal], n: int) -> None:
    if len(s) != n:
        raise ValueError(f"Несовпадение длины ряда: {len(s)} != {n}")
