"""Инвестиционный план: активы и амортизация (см. SPEC §9).

В v0 — линейная амортизация от месяца приобретения в течение срока службы. Переоценка,
продажа активов, незавершённые капвложения — следующие фазы.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class Asset(BaseModel):
    """Основное средство."""

    name: str
    cost: Decimal                  # стоимость приобретения (→ capex, C14)
    purchase_month: int = 0        # месяц приобретения (индекс t)
    life_months: int = 12          # срок службы для линейной амортизации
    # Продажа актива: месяц и цена реализации (→ C16; фин. результат в I20/I21). SPEC §9.
    sale_month: Optional[int] = None
    sale_price: Decimal = Decimal(0)
    # Переоценка: месяц и сумма дооценки (→ B9/остаточная и добавочный капитал B31). SPEC §9.
    revaluation_month: Optional[int] = None
    revaluation_amount: Decimal = Decimal(0)

    def monthly_depreciation(self) -> Decimal:
        if self.life_months <= 0:
            return Decimal(0)
        return self.cost / Decimal(self.life_months)


class InvestmentPlan(BaseModel):
    assets: list[Asset] = Field(default_factory=list)
