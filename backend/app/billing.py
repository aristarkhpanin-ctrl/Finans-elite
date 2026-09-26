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


#: Разделитель перехода в журнале — тот же, что у смены роли участника («было → стало»).
PLAN_CHANGE_ARROW = " → "


def plan_change_details(product: str, was: str, became: str) -> str:
    """Строка журнала о смене тарифа: ``«business: pro → free»``.

    **Запись и чтение — одной парой функций.** В `details` лежал один продукт, а новый
    тариф — в `entity_name`, и запись не отвечала на вопрос «с чего ушли»: отличить уход
    с платного («клиента потеряли») от переключения бесплатного на бесплатный было нечем.
    Отток считается по журналу (F8), и без прежнего тарифа его пришлось бы угадывать.

    Заодно это чинит и сам журнал: «сменил тариф на бесплатный» без прежнего значения —
    запись слабее, чем у смены роли, где «было → стало» стоит с самого начала.
    """
    return f"{product}: {was}{PLAN_CHANGE_ARROW}{became}"


def parse_plan_change(details: str) -> tuple[str, str, str] | None:
    """Разобрать строку обратно: ``(продукт, прежний тариф, новый)``.

    ``None`` — **прежний тариф не назван**: так записаны все смены до F8, где в `details`
    лежал один продукт. Считать их уходом значило бы гадать, а считать «не уходом» —
    врать: метрика называет их отдельным числом и в отток не берёт.
    """
    product, colon, rest = details.partition(":")
    was, arrow, became = rest.partition(PLAN_CHANGE_ARROW)
    if not colon or not arrow:
        return None
    return product.strip(), was.strip(), became.strip()


def is_paid_plan(code: str) -> bool:
    """Платный ли тариф. «По запросу» — **платный**: его условия согласуют вне продукта,
    но бесплатным он от этого не становится, и уход с него — такой же уход."""
    plan = get_plan(code)
    return plan.price_rub > 0 or plan.price_on_request


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
    """6.5a: смена тарифа без внешнего платежа (для разработки/тестов).

    Включает тариф **сразу и без денег** — поэтому в продакшене не выбирается никогда
    (см. :func:`_build_provider`).
    """

    def start_checkout(self, db: Session, org_id: str, plan: Plan, return_url: str,
                       customer_email: str) -> CheckoutResult:
        activate_paid_plan(db, org_id, plan)
        return CheckoutResult(activated=True)


#: Почему в продукте нельзя оплатить. Отказ называет выход: без него клиент, готовый
#: платить, упирается в «ошибку» и уходит — хотя оплата по счёту работает всегда.
PAYMENT_UNAVAILABLE = (
    "Оплата в продукте сейчас не подключена. Тариф можно получить оплатой по счёту: "
    "свяжитесь с платформой — назначение тарифа она сделает сама.")


class UnavailablePaymentProvider(PaymentProvider):
    """Оплата не настроена, а установка — боевая: отказать, а не выдать тариф даром.

    Раньше на этом месте стоял ручной провайдер: без ключей ЮKassa он выбирался при
    **любом** окружении, и в продакшене ``checkout`` включал платный тариф одним запросом
    и без денег — та же дыра, что закрыл F1 на прямой смене тарифа, только через другую
    дверь. Отказ здесь — fail-closed, как у ``JWT_SECRET``: забытая настройка не должна
    превращаться в бесплатный тариф.
    """

    def start_checkout(self, db: Session, org_id: str, plan: Plan, return_url: str,
                       customer_email: str) -> CheckoutResult:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=PAYMENT_UNAVAILABLE)


def _build_provider(app_env: str | None = None, shop_id: str | None = None,
                    secret: str | None = None) -> PaymentProvider:
    """Выбрать провайдера по окружению.

    Ключи ЮKassa заданы → ЮKassa. Нет ключей: вне продакшена — ручной (разработка,
    тесты), в продакшене — **отказ** (:class:`UnavailablePaymentProvider`).
    """
    app_env = os.getenv("APP_ENV", "development") if app_env is None else app_env
    shop_id = os.getenv("YOOKASSA_SHOP_ID") if shop_id is None else shop_id
    secret = os.getenv("YOOKASSA_SECRET_KEY") if secret is None else secret
    if shop_id and secret:
        from .payments_yookassa import YooKassaClient, YooKassaPaymentProvider
        return YooKassaPaymentProvider(YooKassaClient(shop_id, secret))
    if app_env.strip().lower() == "production":
        return UnavailablePaymentProvider()
    return ManualPaymentProvider()


def provider_kind(p: PaymentProvider) -> str:
    """Какой провайдер принимает оплату — для экрана готовности установки (G9)."""
    if isinstance(p, UnavailablePaymentProvider):
        return "unavailable"
    if isinstance(p, ManualPaymentProvider):
        return "manual"
    return "yookassa"


# Текущий провайдер.
provider: PaymentProvider = _build_provider()


def get_payment_provider() -> PaymentProvider:
    """FastAPI-зависимость (переопределяемая в тестах)."""
    return provider
