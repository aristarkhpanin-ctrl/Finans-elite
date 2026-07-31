"""Модель субъекта анализа (Финанс-Аудит): реквизиты, периоды, фактическая отчётность.

Хранится как JSON в таблице ``audit_subjects`` (по образцу ``Project.model``). Значения —
``Decimal`` (строками в JSON), как в расчётном ядре первого продукта. Инвариант «актив =
пассив» проверяется по агрегатам ввода.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .lines import ASSET_CODES, EQLIAB_CODES, INCOME_CODES


class AuditPeriod(BaseModel):
    """Отчётный период: подпись (например «2024» или «2024 Q1») и тип (год/квартал)."""

    label: str = Field(default="", max_length=40)
    kind: Literal["year", "quarter"] = "year"


class AuditSubjectModel(BaseModel):
    """Субъект анализа с фактической отчётностью по периодам.

    ``balance``/``income`` — ``{код строки: [значения по периодам]}`` (длина ряда = числу
    периодов; недостающие/лишние приводятся к ``n`` при чтении). Пустая модель инертна.
    """

    name: str = Field(default="", max_length=255)
    currency: str = Field(default="RUB", max_length=8)
    industry: str = Field(default="", max_length=120)
    periods: list[AuditPeriod] = Field(default_factory=list, max_length=48)
    balance: dict[str, list[Decimal]] = Field(default_factory=dict)
    income: dict[str, list[Decimal]] = Field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.periods)

    def _row(self, table: dict[str, list[Decimal]], code: str) -> list[Decimal]:
        """Ряд строки, приведённый к числу периодов (обрезка/дополнение нулями)."""
        vals = list(table.get(code, []))[: self.n]
        while len(vals) < self.n:
            vals.append(Decimal(0))
        return vals

    def _sum_rows(self, table: dict[str, list[Decimal]], codes: list[str]) -> list[Decimal]:
        out = [Decimal(0)] * self.n
        for code in codes:
            for t, v in enumerate(self._row(table, code)):
                out[t] += v
        return out

    def total_assets(self) -> list[Decimal]:
        return self._sum_rows(self.balance, ASSET_CODES)

    def total_eqliab(self) -> list[Decimal]:
        return self._sum_rows(self.balance, EQLIAB_CODES)

    def balance_gap(self) -> list[Decimal]:
        """Актив − пассив по периодам (0 — баланс сходится)."""
        a, p = self.total_assets(), self.total_eqliab()
        return [a[t] - p[t] for t in range(self.n)]

    def is_balanced(self) -> bool:
        """Баланс сходится во всех периодах (актив = пассив)."""
        return all(g == 0 for g in self.balance_gap())

    def balance_row(self, code: str) -> list[Decimal]:
        return self._row(self.balance, code)

    def has_balance_row(self, code: str) -> bool:
        """Строка введена (а не отсутствует). «Не введено» и «введён ноль» — разные факты:
        диагностика по непредоставленным данным не считается, а не подставляет нули."""
        return bool(self.balance.get(code))

    def income_row(self, code: str) -> list[Decimal]:
        return self._row(self.income, code) if code in INCOME_CODES else [Decimal(0)] * self.n
