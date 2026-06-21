"""Биллинг: текущий тариф организации, контроль квот и абстракция платёжного провайдера.

6.5a — управление тарифом без внешних платежей (смена тарифа напрямую). Реальная
интеграция (ЮKassa, вебхуки, 54-ФЗ) подключается в 6.5b через ``PaymentProvider``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

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


class PaymentProvider(ABC):
    """Абстракция платёжного провайдера (сменяемая реализация)."""

    @abstractmethod
    def change_plan(self, db: Session, org_id: str, plan_code: str):
        """Перевести организацию на тариф (возможно, через платёж)."""


class ManualPaymentProvider(PaymentProvider):
    """6.5a: смена тарифа без внешнего платежа (для разработки/тестов)."""

    def change_plan(self, db: Session, org_id: str, plan_code: str):
        return crud.set_plan(db, org_id, plan_code, status="active")


# Текущий провайдер по умолчанию (в 6.5b заменяется на ЮKassa).
provider: PaymentProvider = ManualPaymentProvider()
