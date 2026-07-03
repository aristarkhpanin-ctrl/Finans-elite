"""Окружение проекта: валюта, инфляция, налоги (см. SPEC §3, §11).

В v0 расчётного ядра используются ставки налогов из настроек проекта; полноценный
многоналоговый движок и индексация по группам инфляции — следующие фазы.
"""
from __future__ import annotations

from decimal import Decimal

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
    """Настраиваемый налог. В v0 ключевые ставки берутся из ProjectSettings."""

    name: str
    rate: Decimal = Decimal(0)
    base: str = ""  # 'sales' | 'profit' | 'property' | 'payroll' | ...


class Environment(BaseModel):
    currencies: list[Currency] = Field(default_factory=lambda: [Currency()])
    inflation: list[InflationGroup] = Field(default_factory=list)
    taxes: list[Tax] = Field(default_factory=list)
    # Курс второй валюты к основной (единиц основной за единицу второй) на конец периода.
    # Пусто = одна валюта (без переоценки). См. SPEC §3, §22.3.
    fx_rate: list[Decimal] = Field(default_factory=list)
    fx_open: Decimal = Decimal(1)  # курс на старте проекта (t = −1), для опорных позиций
