"""Каталог тарифов (статический).

Квоты: ``max_projects`` и ``max_members`` (``None`` — без ограничения). Дополнительные
лимиты (итерации Монте-Карло, доступ к холдингу/what-if) добавляются по мере появления
соответствующего функционала.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    price_rub: int          # цена в месяц, руб. (информационно)
    max_projects: int | None
    max_members: int | None


PLANS: dict[str, Plan] = {
    "free": Plan("free", "Бесплатный", 0, max_projects=5, max_members=5),
    "team": Plan("team", "Команда", 2900, max_projects=50, max_members=25),
    "business": Plan("business", "Бизнес", 9900, max_projects=None, max_members=100),
}

DEFAULT_PLAN = "free"


def get_plan(code: str | None) -> Plan:
    """Тариф по коду; неизвестный/пустой → тариф по умолчанию."""
    if code and code in PLANS:
        return PLANS[code]
    return PLANS[DEFAULT_PLAN]


def is_valid_plan(code: str) -> bool:
    return code in PLANS
