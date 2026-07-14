"""Календарный план: этапы инвестиционной (подготовительной) фазы и ресурсы (SPEC §9).

Аналог раздела «Инвестиционный план → Календарный план» Project Expert. Этапы несут
стоимость по расписанию; тип этапа определяет трактовку (издержка подготовительного периода,
формирование актива или старт производства). См. docs/CALENDAR-PLAN-DECOMPOSITION.md.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .common import AssetCategory

StageKind = Literal["expense", "asset", "production"]
CostTiming = Literal["uniform", "on_finish"]


class Resource(BaseModel):
    """Ресурс (материал/оборудование/труд/услуга) с ценой единицы и условиями оплаты."""

    id: str
    name: str = ""
    unit_price: Decimal = Decimal(0)
    payment_delay_months: int = Field(default=0, ge=0)  # задержка оплаты → кредиторка B23


class StageResource(BaseModel):
    """Потребление ресурса этапом: ссылка на ресурс и количество."""

    resource_id: str
    quantity: Decimal = Decimal(0)


class Stage(BaseModel):
    """Этап календарного плана.

    Стоимость = Σ(ресурс.quantity × Resource.unit_price), либо прямая ``cost`` при отсутствии
    ресурсов. Занимает месяцы ``[start, start+duration)``; завершение = ``start+duration``.
    ``predecessor_id`` (финиш→старт) и ``parent_id`` (иерархия) разрешаются в движке.
    """

    id: str
    name: str = ""
    kind: StageKind = "expense"
    start_month: int = Field(default=0, ge=0)     # абсолютный старт или лаг от предшественника
    duration_months: int = Field(default=1, ge=1)
    predecessor_id: Optional[str] = None
    parent_id: Optional[str] = None               # группа: стоимость несут только листья
    cost: Decimal = Decimal(0)                    # прямая стоимость (если нет ресурсов)
    resources: list[StageResource] = Field(default_factory=list)
    cost_timing: CostTiming = "uniform"
    # kind=expense: 0 → издержка сразу (I21); >0 → РБП (B15) со списанием за N мес. от финиша.
    amortize_months: int = Field(default=0, ge=0)
    # kind=asset:
    asset_life_months: int = Field(default=12, ge=1)
    asset_category: AssetCategory = AssetCategory.EQUIPMENT
    # kind=production: какому продукту этап задаёт старт.
    product_id: Optional[str] = None


class CalendarPlan(BaseModel):
    """Календарный план: этапы + библиотека ресурсов."""

    stages: list[Stage] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
