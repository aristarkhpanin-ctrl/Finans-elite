"""Актуализация (план-факт): фактические данные по прошедшим периодам (SPEC §4.9)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from pydantic import Field, field_validator

from ..decimals import MoneyModel


class Actualization(MoneyModel):
    """Фактические значения строк Кэш-фло по месяцам.

    ``actual_until`` — индекс последнего актуализированного месяца (``-1`` — актуализация
    отсутствует). ``actuals`` — фактические значения листовых строк Кэш-фло
    (код → ряд по месяцам); применяются к периодам ``t <= actual_until``.

    **Пустая ячейка — «факта нет»** (``None``), а не ноль и не ошибка (пакет L, L7): месяц
    остаётся плановым. Вкладка «Факт» прямо показывает заполненность «N из M ячеек», а
    сохранение частично заполненного факта отклонялось целиком — пустую строку модель не
    принимала. Ноль вместо пропуска был бы хуже отказа: «поступлений не было» — другое
    утверждение, чем «факт за месяц ещё не внесён».
    """

    actual_until: int = -1
    actuals: dict[str, list[Optional[Decimal]]] = Field(default_factory=dict)
    #: Сопоставление статей выгрузки ДДС (из 1С или Excel) со строками Кэш-фло:
    #: статья (без регистра и лишних пробелов) → код строки, пусто — «не загружать».
    #: Хранится в модели, чтобы импорт следующего месяца не спрашивал заново. На расчёт
    #: не влияет.
    mapping: dict[str, str] = Field(default_factory=dict)

    @field_validator("actuals", mode="before")
    @classmethod
    def _blank_is_missing(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {code: [None if isinstance(v, str) and not v.strip() else v
                       for v in series] if isinstance(series, list) else series
                for code, series in value.items()}

    @property
    def enabled(self) -> bool:
        return self.actual_until >= 0 and bool(self.actuals)
