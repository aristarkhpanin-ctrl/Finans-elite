"""Показатели эффективности инвестиций (SPEC §17).

Дисконтируется помесячно чистый денежный поток до финансирования (операционная +
инвестиционная деятельность). График инвестиций (потребность в капитале) выделяется по
правилу §22.4 — прирост накопленного дефицита относительно максимума предыдущих
периодов; на нём строятся PI и пиковая потребность в финансировании.
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


def investment_graph(net_flow: Sequence[Decimal]) -> list[Decimal]:
    """График потребности в капитале (SPEC §17, §22.4).

    Инвестиция периода = прирост накопленного дефицита денежных средств относительно
    **максимума дефицита предыдущих периодов** (новый привлекаемый капитал). Ряд
    неотрицателен; его сумма = пиковая потребность в финансировании (наибольший
    накопленный дефицит за горизонт). Операционные «провалы» уже окупившегося проекта
    в инвестиции не попадают.
    """
    inv: list[Decimal] = []
    cum = ZERO
    peak_deficit = ZERO  # максимальный дефицит (−min накопленного потока) за прошедшее
    for cf in net_flow:
        cum += cf
        deficit = -cum if cum < ZERO else ZERO
        if deficit > peak_deficit:
            inv.append(deficit - peak_deficit)
            peak_deficit = deficit
        else:
            inv.append(ZERO)
    return inv


def profitability_index(npv_value: Decimal, pv_investments: Decimal) -> Decimal | None:
    """Индекс доходности: ``PI = 1 + NPV / PV(инвестиции)`` (SPEC §17/§22.4).

    ``pv_investments`` — приведённая потребность в капитале (дисконтированный график
    инвестиций ``investment_graph``). ``None``, если капитал не требовался
    (``pv_investments`` = 0). ``PI > 1`` ⟺ ``NPV > 0``.
    """
    if pv_investments <= ZERO:
        return None
    return ONE + npv_value / pv_investments


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
