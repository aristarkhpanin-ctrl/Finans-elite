"""Финансовые коэффициенты (CALC-ENGINE-SPEC.md §18), 5 групп.

Формулы используют коды строк отчётов (B*, I*, P*). Денежные потоки приводятся к году
множителем ×12 (минимальный шаг расчёта — месяц). Где знаменатель равен нулю — значение
``None``.

Упрощения v0 (к сверке по эталону, SPEC §22):
- оборачиваемость и рентабельность активов/капитала используют **средние за период**
  величины (начало+конец)/2; ликвидность, структура капитала и показатели «на акцию» —
  на конец периода (стандартная трактовка «снимок» vs «поток ÷ средний запас»);
- «закупки» для оборачиваемости кредиторки аппроксимируются строкой I5 (материалы);
- инвестиционные показатели рассчитываются на годовой базе (×12).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from ..money import D
from .statements import Statement

YEAR_MONTHS = Decimal(12)
DAYS = Decimal(365)
TWO = Decimal(2)

RatioSeries = list[Optional[Decimal]]


@dataclass
class FinancialRatios:
    """Группы коэффициентов (код-метка → ряд значений по месяцам)."""

    liquidity: dict[str, RatioSeries] = field(default_factory=dict)
    activity: dict[str, RatioSeries] = field(default_factory=dict)
    gearing: dict[str, RatioSeries] = field(default_factory=dict)
    profitability: dict[str, RatioSeries] = field(default_factory=dict)
    investment: dict[str, RatioSeries] = field(default_factory=dict)


def _div(num: Decimal, den: Decimal) -> Optional[Decimal]:
    """Безопасное деление: ``None`` при нулевом знаменателе."""
    if den == 0:
        return None
    return num / den


def compute_ratios(income: Statement, cashflow: Statement, balance: Statement,
                   profit_use: Statement, common_shares: Decimal, n: int,
                   opening: Optional[dict[str, Decimal]] = None) -> FinancialRatios:
    B = balance
    I = income
    P = profit_use
    no = D(common_shares)
    yr = YEAR_MONTHS
    op = opening or {}

    def avg(code: str, t: int) -> Decimal:
        """Средняя за период величина: (начало + конец)/2 (SPEC §18)."""
        prev = B[code][t - 1] if t > 0 else op.get(code, D(0))
        return (prev + B[code][t]) / TWO

    r = FinancialRatios()

    for t in range(n):
        # на конец периода (ликвидность, структура, на акцию)
        b1, b2, b6, b8 = B["B1"][t], B["B2"][t], B["B6"][t], B["B8"][t]
        b20, b25, b26, b33 = B["B20"][t], B["B25"][t], B["B26"][t], B["B33"][t]
        i1, i4, i5, i7, i8 = I["I1"][t], I["I4"][t], I["I5"][t], I["I7"][t], I["I8"][t]
        i9, i16, i18, i23, i28 = I["I9"][t], I["I16"][t], I["I18"][t], I["I23"][t], I["I28"][t]
        p4, p5 = P["P4"][t], P["P5"][t]

        # средние за период (оборачиваемость, рентабельность активов/капитала)
        a_inv = avg("B3", t) + avg("B4", t) + avg("B5", t)
        a_b2, a_b23 = avg("B2", t), avg("B23", t)
        a_b11, a_b20, a_b33 = avg("B11", t), avg("B20", t), avg("B33", t)
        a_wc = avg("B8", t) - avg("B25", t)

        # --- Ликвидность (на конец периода) ---
        _push(r.liquidity, "Коэффициент текущей ликвидности", _div(b8, b25))
        _push(r.liquidity, "Коэффициент срочной ликвидности", _div(b1 + b2 + b6, b25))
        _push(r.liquidity, "Чистый оборотный капитал", b8 - b25)

        # --- Деловая активность (средние за период) ---
        _push(r.activity, "Период оборачиваемости запасов, дн.", _div(DAYS * a_inv, i7 * yr))
        _push(r.activity, "Период оборачиваемости дебиторки, дн.", _div(DAYS * a_b2, i1 * yr))
        _push(r.activity, "Период оборачиваемости кредиторки, дн.", _div(DAYS * a_b23, i5 * yr))
        _push(r.activity, "Оборачиваемость рабочего капитала", _div(i1 * yr, a_wc))
        _push(r.activity, "Оборачиваемость основных средств", _div(i1 * yr, a_b11))
        _push(r.activity, "Оборачиваемость активов", _div(i1 * yr, a_b20))

        # --- Структура капитала (на конец периода) ---
        _push(r.gearing, "Суммарные обязательства к активам", _div(b25 + b26, b20))
        _push(r.gearing, "Суммарные обязательства к собств. капиталу", _div(b25 + b26, b33))
        _push(r.gearing, "Коэффициент покрытия процентов", _div(i23 + i18, i18))

        # --- Рентабельность (маржа — на конец; ROA/ROE — на средние активы/капитал) ---
        _push(r.profitability, "Рентабельность валовой прибыли", _div(i8, i4))
        _push(r.profitability, "Рентабельность операционной прибыли", _div(i8 - i9 - i16, i4))
        _push(r.profitability, "Рентабельность чистой прибыли", _div(i28, i4))
        _push(r.profitability, "Рентабельность активов (ROA)", _div(i28 * yr, a_b20))
        _push(r.profitability, "Рентабельность собств. капитала (ROE)", _div(i28 * yr, a_b33))

        # --- Инвестиционные (на акцию) ---
        _push(r.investment, "Прибыль на акцию (EPS)", _div((i28 - p4) * yr, no))
        _push(r.investment, "Дивиденды на акцию", _div(p5 * yr, no))
        _push(r.investment, "Коэффициент покрытия дивидендов", _div(i28, p4 + p5))
        _push(r.investment, "Сумма активов на акцию", _div(b20, no))

    return r


def _push(group: dict[str, RatioSeries], key: str, value: Optional[Decimal]) -> None:
    group.setdefault(key, []).append(value)
