"""Общие типы и перечисления для моделей проекта."""
from __future__ import annotations

from enum import Enum


class CostFunction(str, Enum):
    """Функциональное назначение издержки (разнос на строки ОПУ I10–I15)."""

    ADMIN = "admin"                 # административные (I10)
    PRODUCTION = "production"        # производственные (I11)
    MARKETING = "marketing"         # маркетинговые (I12)
    STAFF_ADMIN = "staff_admin"     # зарплата адм. персонала (I13)
    STAFF_PRODUCTION = "staff_production"  # зарплата произв. персонала (I14)
    STAFF_MARKETING = "staff_marketing"    # зарплата маркет. персонала (I15)


class DirectCostKind(str, Enum):
    """Вид прямых издержек (строки ОПУ I5/I6)."""

    MATERIALS = "materials"   # материалы и комплектующие (I5)
    PIECE_WAGES = "piece_wages"  # сдельная зарплата (I6)


class RepaymentType(str, Enum):
    """Схема погашения тела займа."""

    EQUAL_PRINCIPAL = "equal_principal"  # равными долями тела
    BULLET = "bullet"                    # весь возврат в конце срока


class VatBasis(str, Enum):
    """Момент признания НДС к уплате/вычету (SPEC §11, §22.2)."""

    SHIPMENT = "shipment"   # «по отгрузке»: НДС признаётся при начислении (по умолчанию)
    PAYMENT = "payment"     # «по оплате»: НДС признаётся по факту движения денег


class InventoryMethod(str, Enum):
    """Метод оценки себестоимости запасов готовой продукции (SPEC §6, §22.8)."""

    AVERAGE = "average"   # по средней себестоимости (по умолчанию)
    FIFO = "fifo"         # ФИФО: первым списывается самый ранний выпуск


class AssetCategory(str, Enum):
    """Группа основных средств (разнос остаточной стоимости по балансу B12–B14, SPEC §9)."""

    EQUIPMENT = "equipment"   # оборудование (B14) — по умолчанию
    BUILDINGS = "buildings"   # здания и сооружения (B13)
    LAND = "land"             # земля (B12): не амортизируется, вне базы налога на имущество
