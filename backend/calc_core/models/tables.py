"""Таблицы пользователя: произвольные строки-формулы над рядами результата (SPEC «Язык формул»).

Считаются после расчёта отчётов (методику не меняют); ошибка формулы не роняет расчёт —
строка получает сообщение об ошибке и нулевой ряд. См. docs/FORMULA-TABLES-DECOMPOSITION.md.
"""
from __future__ import annotations

from pydantic import Field

from ..decimals import MoneyModel


class UserRow(MoneyModel):
    """Строка таблицы: имя + формула над кодами строк отчётов (I1…, C1…, B1…, P1…, N)."""

    name: str = ""
    formula: str = ""


class UserTable(MoneyModel):
    """Пользовательская таблица: набор строк-формул."""

    id: str
    name: str = ""
    rows: list[UserRow] = Field(default_factory=list)
