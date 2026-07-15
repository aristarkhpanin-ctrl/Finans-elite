"""Операционный план: сбыт, прямые и постоянные издержки (см. SPEC §5–§8).

В v0 принят упрощённый, но согласованный учёт: оплата = начисление (нет дебиторки,
авансов, НДС). Эти эффекты добавляются в следующей фазе с сохранением балансового
инварианта.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

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


class Material(BaseModel):
    """Материал/комплектующая (справочник): цена единицы и условия закупки.

    Потребление задаёт рецептура продукта (``Product.bom``); движок разворачивает её в
    прямые издержки с этими условиями (отсрочка → B23, опережающая закупка → B3,
    ``foreign`` — импорт по курсу закупки с импортным НДС).
    """

    id: str
    name: str = ""
    unit: str = ""                                       # информационно («кг», «шт»)
    unit_price: Decimal = Decimal(0)                     # цена за единицу (при foreign — в валюте)
    payment_delay_months: int = Field(default=0, ge=0)
    stock_lead_months: int = Field(default=0, ge=0)
    foreign: bool = False


class BomLine(BaseModel):
    """Строка рецептуры: норма расхода материала на единицу продукта."""

    material_id: str
    qty_per_unit: Decimal = Decimal(0)


class Product(BaseModel):
    id: str
    name: str
    # Рецептура (BOM): нормы расхода материалов на единицу + сдельная зарплата на единицу.
    # Пустая рецептура — продукт без пер-продуктной себестоимости (как раньше).
    bom: list[BomLine] = Field(default_factory=list)
    piece_wage_per_unit: Decimal = Decimal(0)


class SalesLine(BaseModel):
    """Продажи одного продукта: помесячные объём и цена (без НДС)."""

    product_id: str
    volume: list[Decimal] = Field(default_factory=list)  # натуральный объём по месяцам
    price: list[Decimal] = Field(default_factory=list)    # цена за единицу по месяцам
    payment: PaymentTerms = PaymentTerms()
    # Экспорт во 2-й валюте: цена в валюте, пересчёт выручки/денег/дебиторки по FX[t]
    # (без НДС); валютная дебиторка переоценивается → I25 (SPEC §22.3). По умолчанию — рубли.
    foreign: bool = False
    # Старт продаж: объём до этого месяца обнуляется. Задаётся вручную либо этапом
    # «производство» календарного плана (тот перекрывает ручной старт). None — без гейта.
    start_month: Optional[int] = None


class ProductionLine(BaseModel):
    """План производства продукта (натуральный объём по месяцам).

    Если для продукта план производства не задан, считается «производство под продажи»
    (производство = сбыт), и запасы готовой продукции не образуются.
    """

    product_id: str
    volume: list[Decimal] = Field(default_factory=list)
    # Старт производства (гейт объёма), аналогично сбыту; задаётся этапом «производство».
    start_month: Optional[int] = None


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
    # Материал во 2-й валюте (импорт, без НДС в v0): закупка/сырьё (B3) — по курсу закупки
    # (немонетарный актив, историческая стоимость); валютная кредиторка переоценивается по
    # FX[t] → I25 (рост курса → убыток). Применяется к материалам; по умолчанию — рубли.
    foreign: bool = False


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


class OtherFlow(BaseModel):
    """Прочее поступление/выплата (вне основной деятельности), помесячно.

    Начисление = оплата (в месяце ряда): доход → I20 + C10; выплата → I21 + C11 (вычитаемая)
    либо, при ``from_profit=True``, → I24 + C11 (за счёт прибыли, не уменьшает налоговую базу).
    Инфляцией не индексируется (суммы произвольные).
    """

    name: str
    amount: list[Decimal] = Field(default_factory=list)
    # Только для выплат: невычитаемая (из прибыли) — идёт в I24 вместо I21.
    from_profit: bool = False


class OperatingPlan(BaseModel):
    products: list[Product] = Field(default_factory=list)
    sales: list[SalesLine] = Field(default_factory=list)
    production: list[ProductionLine] = Field(default_factory=list)
    direct_costs: list[DirectCostLine] = Field(default_factory=list)
    fixed_costs: list[FixedCostLine] = Field(default_factory=list)
    # Справочник материалов для рецептур продуктов (Product.bom).
    materials: list[Material] = Field(default_factory=list)
    # Прочие поступления и выплаты (вне основной деятельности) → I20/C10 и I21|I24/C11.
    other_income: list[OtherFlow] = Field(default_factory=list)
    other_expenses: list[OtherFlow] = Field(default_factory=list)
