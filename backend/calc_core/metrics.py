"""Показатели эффективности инвестиций (SPEC §17).

ВНИМАНИЕ (v0): используется упрощённый поток — чистый денежный поток до финансирования
(операционная + инвестиционная деятельность). Точное правило выделения графика
инвестиций по §17/§22 — следующая фаза. Значения помечены как предварительные.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from .money import D, ONE, ZERO
from .series import cumulative


def annual_to_monthly(rate_annual) -> Decimal:
    """Месячная ставка из годовой: (1+R)^(1/12) − 1."""
    r = D(rate_annual)
    return (ONE + r) ** (ONE / D(12)) - ONE


def npv(flow: Sequence[Decimal], monthly_rate: Decimal) -> Decimal:
    """Чистый приведённый доход потока (дисконтирование помесячно от t=0)."""
    acc = ZERO
    for t, cf in enumerate(flow):
        acc += cf / (ONE + monthly_rate) ** t
    return acc


def profitability_index(flow: Sequence[Decimal], monthly_rate: Decimal) -> Decimal | None:
    """PI = дисконт. поступления / |дисконт. инвестиции|."""
    pos = ZERO
    neg = ZERO
    for t, cf in enumerate(flow):
        d = cf / (ONE + monthly_rate) ** t
        if d >= 0:
            pos += d
        else:
            neg += -d
    if neg == 0:
        return None
    return pos / neg


def irr_annual(flow: Sequence[Decimal], lo: Decimal = D("-0.99"),
               hi: Decimal = D("10"), iterations: int = 200) -> Decimal | None:
    """Внутренняя норма рентабельности (годовая) методом бисекции по месячной ставке.

    Возвращает ``None``, если на интервале нет смены знака NPV.
    """
    f_lo = npv(flow, lo)
    f_hi = npv(flow, hi)
    if f_lo == 0:
        return (ONE + lo) ** 12 - ONE
    if f_hi == 0:
        return (ONE + hi) ** 12 - ONE
    if (f_lo > 0) == (f_hi > 0):
        return None  # нет смены знака — IRR не определена на интервале
    a, b = lo, hi
    for _ in range(iterations):
        mid = (a + b) / 2
        f_mid = npv(flow, mid)
        if f_mid == 0:
            break
        if (f_mid > 0) == (f_lo > 0):
            a, f_lo = mid, f_mid
        else:
            b = mid
    monthly = (a + b) / 2
    return (ONE + monthly) ** 12 - ONE


def payback_months(flow: Sequence[Decimal]) -> int | None:
    """Срок окупаемости (мес.): первый период, когда накопленный поток ≥ 0."""
    for t, cum in enumerate(cumulative(flow)):
        if cum >= 0:
            return t + 1
    return None


def discounted_payback_months(flow: Sequence[Decimal], monthly_rate: Decimal) -> int | None:
    """Дисконтированный срок окупаемости (мес.)."""
    discounted = [cf / (ONE + monthly_rate) ** t for t, cf in enumerate(flow)]
    return payback_months(discounted)
