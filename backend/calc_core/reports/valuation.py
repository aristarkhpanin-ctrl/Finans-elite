"""Оценка бизнеса (SPEC §20): стоимость чистых активов и модель Гордона.

v0 — два метода:
- **Чистые активы**: собственный капитал на конец горизонта (B33).
- **Модель Гордона** (капитализация бессрочного потока): ``V = CF·(1+g)/(r−g)``, где
  CF — нормализованный годовой свободный денежный поток (последние ≤12 мес., приведённые
  к году), ``r`` — ставка дисконтирования, ``g`` — темп роста. ``None`` при ``r ≤ g``.

Остальные методы (ликвидационная, чистые активы по рынку, мультипликаторы, DDM) —
следующая фаза. Конкретные конвенции (база CF, период нормализации) — к сверке по эталону.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from ..money import D, ONE, ZERO
from .statements import Statement


@dataclass
class BusinessValuation:
    net_assets: Decimal = ZERO                 # собственный капитал на конец (B33)
    gordon_value: Optional[Decimal] = None     # капитализация по модели Гордона


def compute_valuation(balance: Statement, cashflow: Statement, discount_rate_annual,
                      growth_rate, n: int) -> BusinessValuation:
    if n <= 0:
        return BusinessValuation()
    net_assets = balance["B33"][n - 1]

    # Нормализованный годовой свободный денежный поток: последние ≤12 месяцев → к году.
    k = min(12, n)
    tail = sum((cashflow["C13"][t] + cashflow["C20"][t] for t in range(n - k, n)), ZERO)
    annual_fcf = tail / D(k) * D(12)

    r, g = D(discount_rate_annual), D(growth_rate)
    gordon = annual_fcf * (ONE + g) / (r - g) if r > g else None
    return BusinessValuation(net_assets=net_assets, gordon_value=gordon)
