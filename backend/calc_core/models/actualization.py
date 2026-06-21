"""Актуализация (план-факт): фактические данные по прошедшим периодам (SPEC §4.9)."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class Actualization(BaseModel):
    """Фактические значения строк Кэш-фло по месяцам.

    ``actual_until`` — индекс последнего актуализированного месяца (``-1`` — актуализация
    отсутствует). ``actuals`` — фактические значения листовых строк Кэш-фло
    (код → ряд по месяцам); применяются к периодам ``t <= actual_until``.
    """

    actual_until: int = -1
    actuals: dict[str, list[Decimal]] = Field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return self.actual_until >= 0 and bool(self.actuals)
