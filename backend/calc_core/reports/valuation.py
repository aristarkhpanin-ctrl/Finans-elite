"""Оценка бизнеса (SPEC §20): чистые активы, модель Гордона, DDM, мультипликатор прибыли.

Методы v0:
- **Чистые активы**: собственный капитал на конец горизонта (B33).
- **Модель Гордона** (капитализация бессрочного свободного потока): ``V = CF·(1+g)/(r−g)``,
  CF — нормализованный годовой свободный денежный поток (последние ≤12 мес. → к году).
- **DDM** (капитализация дивидендов): ``V = Div·(1+g)/(r−g)`` на нормализованных годовых
  дивидендах (C26). ``None`` при ``r ≤ g``.
- **Мультипликатор прибыли**: ``V = множитель · годовая чистая прибыль`` (I28). ``None`` при
  нулевом множителе.
- **Ликвидационная стоимость**: ``V = доля_возврата · активы − обязательства`` на конец
  горизонта (``доля_возврата·B20 − (B20−B33)``); ``None`` при нулевой доле возврата.

Нормализация — последние ≤12 месяцев, приведённые к году. Рыночные чистые активы и точные
конвенции — к сверке по эталону.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from ..money import D, ONE, ZERO
from .statements import Statement


@dataclass
class BusinessValuation:
    net_assets: Decimal = ZERO                      # собственный капитал на конец (B33)
    gordon_value: Optional[Decimal] = None          # капитализация свободного потока (Гордон)
    dividend_value: Optional[Decimal] = None        # капитализация дивидендов (DDM)
    earnings_multiple_value: Optional[Decimal] = None  # множитель × годовая прибыль
    liquidation_value: Optional[Decimal] = None     # ликвидационная стоимость


def _annualized(series: list[Decimal], n: int, k: int) -> Decimal:
    """Сумма последних ``k`` месяцев, приведённая к году."""
    tail = sum((series[t] for t in range(n - k, n)), ZERO)
    return tail / D(k) * D(12)


def compute_valuation(income: Statement, cashflow: Statement, balance: Statement,
                      discount_rate_annual, growth_rate, earnings_multiple,
                      liquidation_recovery, n: int) -> BusinessValuation:
    if n <= 0:
        return BusinessValuation()
    net_assets = balance["B33"][n - 1]

    # Нормализованные годовые величины (последние ≤12 месяцев → к году).
    k = min(12, n)
    annual_fcf = _annualized([cashflow["C13"][t] + cashflow["C20"][t] for t in range(n)], n, k)
    annual_dividends = _annualized(cashflow["C26"], n, k)
    annual_earnings = _annualized(income["I28"], n, k)

    r, g = D(discount_rate_annual), D(growth_rate)
    capit = (ONE + g) / (r - g) if r > g else None  # множитель капитализации Гордона
    gordon = annual_fcf * capit if capit is not None else None
    dividend = annual_dividends * capit if capit is not None else None

    mult = D(earnings_multiple)
    earnings_value = mult * annual_earnings if mult > 0 else None

    # Ликвидация: возвратная стоимость активов за вычетом обязательств (B20−B33 = долг).
    recovery = D(liquidation_recovery)
    total_assets = balance["B20"][n - 1]
    liabilities = total_assets - net_assets
    liquidation = recovery * total_assets - liabilities if recovery > 0 else None

    return BusinessValuation(
        net_assets=net_assets,
        gordon_value=gordon,
        dividend_value=dividend,
        earnings_multiple_value=earnings_value,
        liquidation_value=liquidation,
    )
