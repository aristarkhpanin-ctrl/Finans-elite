"""Операционный план: сбыт, прямые и постоянные издержки (см. SPEC §5–§8).

В v0 принят упрощённый, но согласованный учёт: оплата = начисление (нет дебиторки,
авансов, НДС). Эти эффекты добавляются в следующей фазе с сохранением балансового
инварианта.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from .common import CostFunction, DirectCostKind


class PaymentTerms(BaseModel):
    """Условия оплаты продаж (SPEC §5).

    Доля ``prepayment_share`` поступает предоплатой за ``advance_lead_months`` до поставки
    (формирует авансы, B24). Остаток поступает через ``payment_delay_months`` после
    поставки (формирует дебиторку, B2).
    """

    prepayment_share: Decimal = Field(default=Decimal(0), ge=0, le=1)
    advance_lead_months: int = Field(default=0, ge=0)
    payment_delay_months: int = Field(default=0, ge=0)


class Product(BaseModel):
    id: str
    name: str


class SalesLine(BaseModel):
    """Продажи одного продукта: помесячные объём и цена (без НДС)."""

    product_id: str
    volume: list[Decimal] = Field(default_factory=list)  # натуральный объём по месяцам
    price: list[Decimal] = Field(default_factory=list)    # цена за единицу по месяцам
    payment: PaymentTerms = PaymentTerms()
    # Экспорт во 2-й валюте: цена в валюте, пересчёт выручки/денег/дебиторки по FX[t]
    # (без НДС); валютная дебиторка переоценивается → I25 (SPEC §22.3). По умолчанию — рубли.
    foreign: bool = False


class ProductionLine(BaseModel):
    """План производства продукта (натуральный объём по месяцам).

    Если для продукта план производства не задан, считается «производство под продажи»
    (производство = сбыт), и запасы готовой продукции не образуются.
    """

    product_id: str
    volume: list[Decimal] = Field(default_factory=list)


class DirectCostLine(BaseModel):
    """Прямая издержка (материалы или сдельная зарплата), помесячно.

    ``amount`` — стоимость, относимая к производству месяца (себестоимость капитализуется
    в запасах готовой продукции и признаётся при продаже, SPEC §6).
    """

    name: str
    kind: DirectCostKind = DirectCostKind.MATERIALS
    amount: list[Decimal] = Field(default_factory=list)
    payment_delay_months: int = Field(default=0, ge=0)  # задержка оплаты → кредиторка (B23)
    stock_lead_months: int = Field(default=0, ge=0)     # опережающая закупка → сырьё (B3)


class FixedCostLine(BaseModel):
    """Постоянная (общая) издержка с функциональным разносом, помесячно."""

    name: str
    function: CostFunction = CostFunction.ADMIN
    amount: list[Decimal] = Field(default_factory=list)
    payment_delay_months: int = Field(default=0, ge=0)  # задержка оплаты → кредиторка (B23)
    # «Из прибыли»: невычитаемая издержка — идёт в I24, не уменьшает налоговую базу.
    from_profit: bool = False
    # Издержка во 2-й валюте (услуга, без НДС): пересчёт по FX[t], валютная кредиторка
    # переоценивается → I25 (рост курса → убыток). По умолчанию — основная валюта.
    foreign: bool = False


class OperatingPlan(BaseModel):
    products: list[Product] = Field(default_factory=list)
    sales: list[SalesLine] = Field(default_factory=list)
    production: list[ProductionLine] = Field(default_factory=list)
    direct_costs: list[DirectCostLine] = Field(default_factory=list)
    fixed_costs: list[FixedCostLine] = Field(default_factory=list)
