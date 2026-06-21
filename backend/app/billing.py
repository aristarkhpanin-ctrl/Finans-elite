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
from .plans import Plan, get_plan


def current_plan(db: Session, org_id: str) -> Plan:
    """Действующий тариф организации (при отсутствии подписки — тариф по умолчанию)."""
    sub = crud.get_subscription(db, org_id)
    return get_plan(sub.plan_code if sub else None)


def ensure_project_quota(db: Session, org_id: str) -> None:
    plan = current_plan(db, org_id)
    if plan.max_projects is not None and crud.count_projects(db, org_id) >= plan.max_projects:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Достигнут лимит проектов тарифа «{plan.name}» ({plan.max_projects}). "
                   f"Перейдите на более высокий тариф.",
        )


def ensure_member_quota(db: Session, org_id: str) -> None:
    plan = current_plan(db, org_id)
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

    def handle_webhook(self, db: Session, event: dict) -> None:
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
