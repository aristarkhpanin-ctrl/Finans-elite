"""Окружение проекта: валюта, инфляция, налоги (см. SPEC §3, §11, §22.9).

Ключевые ставки (прибыль/имущество/НДС/с продаж/взносы) — в ProjectSettings;
``Environment.taxes`` — произвольные настраиваемые налоги поверх них (SPEC §22.9).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class Currency(BaseModel):
    """Валюта проекта."""

    code: str = "RUB"
    name: str = "Российский рубль"


class InflationGroup(BaseModel):
    """Группа инфляции (годовые ставки помесячно). Зарезервировано для следующей фазы."""

    name: str
    annual_rates: list[Decimal] = Field(default_factory=list)


class Tax(BaseModel):
    """Настраиваемый налог (SPEC §22.9): ставка × база, периодичность уплаты, отнесение.

    База считается по показателям **до настраиваемых налогов** (предварительный прогон):
    пресеты — выручка (I1), загруженный ФОТ (I6+I13+I14+I15), имущество (B13+B14),
    прибыль (МАКС(I26, 0)) — либо произвольная формула языка формул (base='formula').
    """

    name: str
    rate: Decimal = Decimal(0)
    base: Literal["revenue", "payroll", "property", "profit", "formula"] = "revenue"
    formula: str = ""            # база-формула при base='formula'
    # Уплата: месяц — в месяце начисления; квартал/год — в последнем месяце периода
    # проекта; неуплаченный остаток — в B21 (отсроченные налоговые платежи).
    periodicity: Literal["month", "quarter", "year"] = "month"
    # Отнесение: вычитаемые (→ I21) либо за счёт прибыли (→ I24, базу прибыли не уменьшают).
    allocation: Literal["expense", "profit"] = "expense"


class Environment(BaseModel):
    currencies: list[Currency] = Field(default_factory=lambda: [Currency()])
    inflation: list[InflationGroup] = Field(default_factory=list)
    taxes: list[Tax] = Field(default_factory=list)
    # Курс второй валюты к основной (единиц основной за единицу второй) на конец периода.
    # Пусто = одна валюта (без переоценки). См. SPEC §3, §22.3.
    fx_rate: list[Decimal] = Field(default_factory=list)
    fx_open: Decimal = Decimal(1)  # курс на старте проекта (t = −1), для опорных позиций
