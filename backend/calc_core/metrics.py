"""Показатели эффективности инвестиций (SPEC §17).

Дисконтируется помесячно чистый денежный поток до финансирования (операционная +
инвестиционная деятельность). График инвестиций (потребность в капитале) выделяется по
правилу §22.4 — прирост накопленного дефицита относительно максимума предыдущих
периодов; на нём строятся PI и пиковая потребность в финансировании.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from .money import ONE, ZERO, D
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


#: Причина, по которой нормы доходности на вложенное не считаются. Едет вместе с
#: отсутствующими числами — на экран, в документ и в снимок: «—» без объяснения читается
#: как «ноль» или «не посчитали», а это третье состояние.
NO_INVESTMENT_NOTE = (
    "Поток начинается с притока: это действующий бизнес, живущий на своём обороте, а не "
    "вложение. Нормы доходности на вложенное (IRR, MIRR, ARR, PI) к нему неприменимы — "
    "делить прибыль не на что. NPV и потребность в финансировании считаются как обычно."
)


def has_investment(flow: Sequence[Decimal]) -> bool:
    """Содержит ли поток вложение: первый ненулевой элемент отрицателен (SPEC §17).

    Одно условие на всё семейство «доходности **на вложенное**» — IRR, MIRR, ARR, PI.
    Разойтись им нельзя: пользователь, у которого «IRR не определена» стоит рядом с
    «PI 43,9», получает два противоположных ответа на один вопрос и верит тому, который
    больше нравится. Именно это и происходило с действующим бизнесом: IRR отказывалась,
    а PI делил двадцать миллионов NPV на случайный кассовый провал в полмиллиона.
    """
    first = next((cf for cf in flow if cf != 0), ZERO)
    return first < ZERO


def profitability_index(npv_value: Decimal, pv_investments: Decimal,
                        flow: Sequence[Decimal] | None = None) -> Decimal | None:
    """Индекс доходности: ``PI = 1 + NPV / PV(инвестиции)`` (SPEC §17/§22.4).

    ``pv_investments`` — приведённая потребность в капитале (дисконтированный график
    инвестиций ``investment_graph``). ``PI > 1`` ⟺ ``NPV > 0``.

    ``None`` в двух случаях: капитал не требовался вовсе (``pv_investments`` = 0) и —
    если передан ``flow`` — поток вложения не содержит (:func:`has_investment`). Во
    втором знаменатель формально не ноль, но он и не инвестиция: у действующего бизнеса
    туда попадает случайный кассовый провал, и индекс выходит в десятки.
    """
    if pv_investments <= ZERO:
        return None
    if flow is not None and not has_investment(flow):
        return None
    return ONE + npv_value / pv_investments


def irr_annual(flow: Sequence[Decimal], lo: Decimal = D("-0.99"),
               hi: Decimal = D("10"), iterations: int = 200) -> Decimal | None:
    """Внутренняя норма рентабельности (годовая) методом бисекции по месячной ставке.

    Возвращает ``None``, если IRR к этому потоку **неприменима**.

    Первое условие — вложение. IRR это норма доходности **на вложенное**; поток, который
    начинается с притока (действующий бизнес, живущий на своём обороте), вложения не
    содержит, и числа у такой «доходности» нет. Без этой проверки бисекция всё равно
    что-нибудь возвращала: у потока с отрицательным хвостом знак NPV на границе
    интервала меняется, и ответом становилась граница — «−100% годовых» под прибыльным
    магазином. Неверное число хуже честного «не определена»: его читают.

    Второе условие — смена знака NPV на интервале (иначе корня там просто нет).
    """
    if not has_investment(flow):
        return None
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


def mirr_annual(flow: Sequence[Decimal], finance_rate_m: Decimal,
                reinvest_rate_m: Decimal) -> Decimal | None:
    """Модифицированная IRR (годовая): один корень всегда (в отличие от IRR).

    Притоки наращиваются к концу горизонта по ставке реинвестиций, оттоки приводятся к
    началу по ставке финансирования: ``MIRR_м = (FV/|PV|)^(1/(n−1)) − 1``. None, если нет
    притоков или оттоков (показатель не определён) — и, как у IRR, если поток вложения не
    содержит (:func:`has_investment`): «один корень всегда» относится к разрешимости
    уравнения, а не к осмысленности ответа.
    """
    n = len(flow)
    if n < 2 or not has_investment(flow):
        return None
    fv = ZERO   # будущая стоимость притоков на конец горизонта
    pv = ZERO   # приведённая стоимость оттоков на начало (отрицательная)
    for t, cf in enumerate(flow):
        if cf > 0:
            fv += cf * (ONE + reinvest_rate_m) ** (n - 1 - t)
        elif cf < 0:
            pv += cf / (ONE + finance_rate_m) ** t
    if fv <= 0 or pv >= 0:
        return None
    mirr_m = (fv / -pv) ** (ONE / D(n - 1)) - ONE
    return (ONE + mirr_m) ** 12 - ONE


def arr_annual(flow: Sequence[Decimal]) -> Decimal | None:
    """Средняя норма рентабельности (ARR, годовая).

    Среднегодовые поступления (Σ положительных элементов чистого потока / число лет) к
    потребности в капитале (Σ графика инвестиций §22.4). None без инвестиций — и когда
    поток вложения не содержит (:func:`has_investment`): у действующего бизнеса в
    знаменателе оказывается случайный кассовый провал, и ARR выходит в тысячи процентов.
    """
    inv_total = ZERO
    for v in investment_graph(flow):
        inv_total += v
    if inv_total <= 0 or not flow or not has_investment(flow):
        return None
    inflows = ZERO
    for cf in flow:
        if cf > 0:
            inflows += cf
    years = D(len(flow)) / D(12)
    return (inflows / years) / inv_total
