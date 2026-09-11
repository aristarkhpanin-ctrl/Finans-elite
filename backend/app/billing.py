"""Биллинг: тариф организации, контроль квот и платёжный провайдер.

- Квоты тарифа проверяются при создании проекта/добавлении участника (превышение → 402).
- Смена тарифа: ручной провайдер (6.5a, мгновенно) или через платёж ЮKassa (6.5b).
  Провайдер выбирается по окружению (``YOOKASSA_SHOP_ID``/``YOOKASSA_SECRET_KEY``).
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from . import crud
from .plans import UNIT_NAME, Plan, get_plan


def current_plan(db: Session, org_id: str, product: str = "business") -> Plan:
    """Действующий тариф организации по продукту (без подписки — тариф по умолчанию)."""
    sub = crud.get_subscription(db, org_id, product)
    return get_plan(sub.plan_code if sub else None, product)


def _ensure_unit_quota(db: Session, org_id: str, product: str, used: int) -> None:
    """Общая проверка квоты единиц продукта: проектов у «Элит», дел у «Аудита».

    Одна функция на оба продукта не ради краткости: разойдясь, две копии однажды дали
    бы разный ответ на один и тот же вопрос «можно ли завести ещё».
    """
    plan = current_plan(db, org_id, product)
    if plan.max_units is not None and used >= plan.max_units:
        unit = UNIT_NAME.get(product, "объектов")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Достигнут лимит {unit} тарифа «{plan.name}» ({plan.max_units}). "
                   f"Перейдите на более высокий тариф.",
        )


def ensure_project_quota(db: Session, org_id: str) -> None:
    _ensure_unit_quota(db, org_id, "business", crud.count_projects(db, org_id))


def ensure_case_quota(db: Session, org_id: str) -> None:
    """Квота дел «Финанс-Аудит».

    До этого дела не считались вовсе: ``ensure_project_quota`` смотрел только проекты,
    а создание дела квоту не вызывало — на любом тарифе, включая бесплатный, дел можно
    было завести сколько угодно.
    """
    _ensure_unit_quota(db, org_id, "audit", crud.count_audit_subjects(db, org_id))


def ensure_member_quota(db: Session, org_id: str, product: str = "business") -> None:
    plan = current_plan(db, org_id, product)
    if plan.max_members is not None and crud.count_members(db, org_id) >= plan.max_members:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Достигнут лимит участников тарифа «{plan.name}» ({plan.max_members}). "
                   f"Перейдите на более высокий тариф.",
        )


@dataclass
class CheckoutResult:
    """Результат инициации смены тарифа."""

    activated: bool                 # тариф активирован сразу (ручной провайдер)
    payment_id: str | None = None
    confirmation_url: str | None = None  # ссылка на оплату (ЮKassa)


class PaymentProvider(ABC):
    """Абстракция платёжного провайдера (сменяемая реализация)."""

    @abstractmethod
    def start_checkout(self, db: Session, org_id: str, plan: Plan, return_url: str,
                       customer_email: str) -> CheckoutResult:
        """Инициировать смену тарифа (сразу или через платёж)."""

    def handle_webhook(self, db: Session, event: dict) -> None:  # noqa: B027 — необязательный хук (провайдер переопределяет по желанию)
        """Обработать уведомление провайдера (по умолчанию — игнор)."""


class ManualPaymentProvider(PaymentProvider):
    """6.5a: смена тарифа без внешнего платежа (для разработки/тестов)."""

    def start_checkout(self, db: Session, org_id: str, plan: Plan, return_url: str,
                       customer_email: str) -> CheckoutResult:
        crud.set_plan(db, org_id, plan.code, status="active")
        return CheckoutResult(activated=True)


def _build_provider() -> PaymentProvider:
    """Выбрать провайдера по окружению: ЮKassa при наличии ключей, иначе ручной."""
    shop_id = os.getenv("YOOKASSA_SHOP_ID")
    secret = os.getenv("YOOKASSA_SECRET_KEY")
    if shop_id and secret:
        from .payments_yookassa import YooKassaClient, YooKassaPaymentProvider
        return YooKassaPaymentProvider(YooKassaClient(shop_id, secret))
    return ManualPaymentProvider()


# Текущий провайдер.
provider: PaymentProvider = _build_provider()


def get_payment_provider() -> PaymentProvider:
    """FastAPI-зависимость (переопределяемая в тестах)."""
    return provider
