"""Каталог тарифов — свой на каждый продукт платформы.

Продукты продаются порознь: «Финанс-Элит» (бизнес-планирование) и «Финанс-Аудит»
(проверка фирмы-цели) покупают разные люди для разных задач, и общий каталог означал
бы, что цена одного меняется при пересмотре цен другого.

Поэтому у организации **своя подписка на каждый продукт** (``subscriptions`` уникальна
по паре организация + продукт), а коды тарифов уникальны глобально: по одному коду
всегда понятно, о каком продукте речь, и оформление платежа не нужно параметризовать
продуктом отдельно.

Единица квоты у продуктов разная — проект у «Элит», дело у «Аудита», — поэтому поле
называется ``max_units``, а не ``max_projects``: имя, которое верно лишь для половины
каталога, рано или поздно прочитают буквально.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Product = Literal["business", "audit"]

PRODUCTS: tuple[Product, ...] = ("business", "audit")


@dataclass(frozen=True)
class Plan:
    code: str
    product: Product
    name: str
    price_rub: int              # в месяц, руб.; 0 при price_on_request
    max_units: int | None       # проектов («Элит») / дел («Аудит»); None — без ограничения
    max_members: int | None
    #: Цена «по запросу»: корпоративные условия не выражаются числом, и подставлять
    #: вместо них ноль нельзя — на экране это выглядело бы как бесплатный тариф.
    price_on_request: bool = False


#: Как называется единица квоты в каждом продукте (для подписи на экране тарифа).
UNIT_NAME: dict[str, str] = {"business": "проектов", "audit": "дел"}


PLANS: dict[str, Plan] = {
    # «Финанс-Элит» — прежний прайс, не меняется.
    "free": Plan("free", "business", "Бесплатный", 0, max_units=5, max_members=5),
    "team": Plan("team", "business", "Команда", 2900, max_units=50, max_members=25),
    "business": Plan("business", "business", "Бизнес", 9900,
                     max_units=None, max_members=100),
    # «Финанс-Аудит» — прайс из макетов (Экран 16).
    # Пробный повторяет бесплатный тариф «Элит» по щедрости (5 единиц, 5 мест) — иначе
    # демо-дело съело бы всю квоту, и первым, что увидел бы новый пользователь после
    # знакомства с продуктом, был бы отказ завести собственное дело.
    "audit_trial": Plan("audit_trial", "audit", "Пробный", 0, max_units=5, max_members=5),
    "audit_team": Plan("audit_team", "audit", "Команда", 24000,
                       max_units=10, max_members=8),
    "audit_corp": Plan("audit_corp", "audit", "Корпоративный", 0,
                       max_units=None, max_members=None, price_on_request=True),
}

#: Тариф по умолчанию для каждого продукта (на него попадает новая организация).
DEFAULT_PLANS: dict[str, str] = {"business": "free", "audit": "audit_trial"}

#: Совместимость: тариф по умолчанию первого продукта (используется при создании
#: организации, у которой подписка на «Элит» заводится сразу).
DEFAULT_PLAN = DEFAULT_PLANS["business"]

# Разовая проверка «45 000 ₽ за дело» из макета здесь намеренно отсутствует. Это
# оплата за использование, а не подписка: её нельзя выразить тарифом с квотой в одно
# дело, потому что счёт выставляется на каждое заведённое дело, а не раз в месяц.
# Заводить такой «тариф» значило бы изобразить биллинг, которого нет: платёжный поток
# в payments_yookassa начинается со смены тарифа, а не с создания сущности.


def plans_for(product: str) -> list[Plan]:
    """Каталог тарифов продукта в порядке возрастания возможностей."""
    return [p for p in PLANS.values() if p.product == product]


def get_plan(code: str | None, product: str = "business") -> Plan:
    """Тариф по коду; неизвестный/пустой → тариф по умолчанию **этого продукта**.

    Продукт нужен именно для подстановки умолчания: молча вернув бесплатный тариф
    «Элит» на неизвестный код аудита, мы дали бы организации чужие квоты.
    """
    if code and code in PLANS:
        return PLANS[code]
    return PLANS[DEFAULT_PLANS.get(product, DEFAULT_PLAN)]


def is_valid_plan(code: str) -> bool:
    return code in PLANS


def product_of(code: str) -> str:
    """Продукт, к которому относится код тарифа (неизвестный → «Элит»)."""
    plan = PLANS.get(code)
    return plan.product if plan else "business"
