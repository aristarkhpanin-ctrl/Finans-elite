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
