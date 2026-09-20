"""Биллинг: тариф организации, контроль квот и платёжный провайдер.

- Квоты тарифа проверяются при создании проекта/добавлении участника (превышение → 402).
- Смена тарифа: ручной провайдер (6.5a, мгновенно) или через платёж ЮKassa (6.5b).
  Провайдер выбирается по окружению (``YOOKASSA_SHOP_ID``/``YOOKASSA_SECRET_KEY``).
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from . import crud
from .billing_period import paid_period_end
from .plans import UNIT_NAME, Plan, get_plan


def activate_paid_plan(db: Session, org_id: str, plan: Plan,
                       paid_at: datetime | None = None, months: int = 1):
    """Включить тариф **по факту оплаты** — и начать отсчёт оплаченного периода.

    Одна дверь на **всех**, кто проводит оплату: ручной провайдер (разработка), ЮKassa и
    оператор платформы, проводящий оплату по счёту (F1). Раньше каждый звал ``set_plan``
    сам, и добавить срок пришлось бы в трёх местах — ровно так и появляются подписки,
    которые истекают у одних клиентов и не истекают у других.

    ``months`` — сколько периодов оплачено сразу; у провайдеров это всегда один, и
    умолчание оставляет их поведение прежним.
    """
    end = paid_period_end(plan, paid_at or datetime.now(timezone.utc), months)
    return crud.set_plan(db, org_id, plan.code, status="active", product=plan.product,
                         period_end=end, paid=True)


#: Что клиенту разрешено менять самому. Платный тариф выдаёт **платёж**, а не право
#: `billing.manage`: оно есть у владельца организации-клиента, и прямая смена была
#: способом взять «Корпоративный» бесплатно и навсегда (срок при ней не ставился вовсе).
#:
#: Уйти на бесплатный — по-прежнему его право и его решение: это отказ от услуги, а не
#: её получение. Квота при этом падает, и отказ на следующем сохранении объяснит себя
#: сам — как и у неплательщика.
def is_self_service(plan: Plan) -> bool:
    """Может ли клиент перейти на этот тариф сам, без оплаты."""
    return plan.price_rub <= 0 and not plan.price_on_request


def current_plan(db: Session, org_id: str, product: str = "business") -> Plan:
    """Действующий тариф организации по продукту (без подписки — тариф по умолчанию)."""
    sub = crud.get_subscription(db, org_id, product)
    return get_plan(sub.plan_code if sub else None, product)


#: Чем меряется квота единиц у каждого продукта: проектами у «Элит», делами у «Аудита».
#:
#: **Одна карта на проверку и на показ.** Экран сводки (F7) считает «осталось» отсюда же,
#: чем отказывает создание: посчитай он сам, и однажды показал бы «осталось 2» там, где
#: сохранение уже отвечает 402, — а клиент пошёл бы в поддержку с двумя правдами сразу.
#: Перечень закрыт: продукт без своей меры роняет тест.
UNIT_COUNT: dict[str, Callable[[Session, str], int]] = {
    "business": crud.count_projects,
    "audit": crud.count_audit_subjects,
}


def units_used(db: Session, org_id: str, product: str) -> int:
    """Сколько единиц квоты израсходовано — тем же счётом, что и в проверке."""
    counter = UNIT_COUNT.get(product)
    return counter(db, org_id) if counter is not None else 0


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
    _ensure_unit_quota(db, org_id, "business", units_used(db, org_id, "business"))


def ensure_case_quota(db: Session, org_id: str) -> None:
    """Квота дел «Финанс-Аудит».

    До этого дела не считались вовсе: ``ensure_project_quota`` смотрел только проекты,
    а создание дела квоту не вызывало — на любом тарифе, включая бесплатный, дел можно
    было завести сколько угодно.
    """
    _ensure_unit_quota(db, org_id, "audit", units_used(db, org_id, "audit"))


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
        activate_paid_plan(db, org_id, plan)
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
