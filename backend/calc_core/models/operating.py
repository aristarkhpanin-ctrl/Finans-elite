"""Операционный план: сбыт, прямые и постоянные издержки (см. SPEC §5–§8).

В v0 принят упрощённый, но согласованный учёт: оплата = начисление (нет дебиторки,
авансов, НДС). Эти эффекты добавляются в следующей фазе с сохранением балансового
инварианта.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from .common import CostFunction, DirectCostKind


class Product(BaseModel):
    id: str
    name: str


class SalesLine(BaseModel):
    """Продажи одного продукта: помесячные объём и цена (без НДС)."""

    product_id: str
    volume: list[Decimal] = Field(default_factory=list)  # натуральный объём по месяцам
    price: list[Decimal] = Field(default_factory=list)    # цена за единицу по месяцам


class DirectCostLine(BaseModel):
    """Прямая издержка (материалы или сдельная зарплата), помесячно."""

    name: str
    kind: DirectCostKind = DirectCostKind.MATERIALS
    amount: list[Decimal] = Field(default_factory=list)


class FixedCostLine(BaseModel):
    """Постоянная (общая) издержка с функциональным разносом, помесячно."""

    name: str
    function: CostFunction = CostFunction.ADMIN
    amount: list[Decimal] = Field(default_factory=list)


class OperatingPlan(BaseModel):
    products: list[Product] = Field(default_factory=list)
    sales: list[SalesLine] = Field(default_factory=list)
    direct_costs: list[DirectCostLine] = Field(default_factory=list)
    fixed_costs: list[FixedCostLine] = Field(default_factory=list)
