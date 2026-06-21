"""Интеграция с ЮKassa (6.5b).

``YooKassaClient`` инкапсулирует HTTP-вызовы к API ЮKassa (в тестах подменяется фейком),
``YooKassaPaymentProvider`` реализует флоу: создать платёж → вернуть ссылку оплаты →
по вебхуку ``payment.succeeded`` активировать тариф (идемпотентно).

Безопасность вебхука в продакшене: ограничение по IP-адресам ЮKassa и/или повторный
запрос статуса платежа через API. Здесь обрабатывается только платёж, известный в БД
(по ``provider_payment_id``), и переход в ``succeeded`` выполняется один раз.

54-ФЗ: в платёж включается чек (``receipt``) с email покупателя и позицией тарифа.
``YOOKASSA_VAT_CODE`` — код ставки НДС для чека (по умолчанию 1 — «без НДС»).
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from . import crud
from .billing import CheckoutResult, PaymentProvider
from .plans import Plan

API_BASE = os.getenv("YOOKASSA_API_BASE", "https://api.yookassa.ru/v3")
VAT_CODE = int(os.getenv("YOOKASSA_VAT_CODE", "1"))  # 1 — без НДС


class YooKassaClient:
    """Тонкий клиент API ЮKassa (HTTP Basic: shop_id:secret_key)."""

    def __init__(self, shop_id: str, secret_key: str, base_url: str = API_BASE):
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.base_url = base_url

    def create_payment(self, payload: dict, idempotence_key: str) -> dict:
        import httpx  # импорт здесь, чтобы зависимость требовалась только при боевом провайдере

        resp = httpx.post(
            f"{self.base_url}/payments",
            json=payload,
            auth=(self.shop_id, self.secret_key),
            headers={"Idempotence-Key": idempotence_key},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


class YooKassaPaymentProvider(PaymentProvider):
    def __init__(self, client: YooKassaClient):
        self.client = client

    def start_checkout(self, db: Session, org_id: str, plan: Plan, return_url: str,
                       customer_email: str) -> CheckoutResult:
        payment = crud.create_payment(db, org_id, plan.code, plan.price_rub, provider="yookassa")
        amount = {"value": f"{plan.price_rub}.00", "currency": "RUB"}
        payload = {
            "amount": amount,
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": f"Тариф «{plan.name}»",
            "metadata": {"organization_id": org_id, "plan_code": plan.code, "payment_id": payment.id},
            "receipt": {  # 54-ФЗ
                "customer": {"email": customer_email},
                "items": [{
                    "description": f"Подписка: тариф «{plan.name}»",
                    "quantity": "1.00",
                    "amount": amount,
                    "vat_code": VAT_CODE,
                    "payment_mode": "full_payment",
                    "payment_subject": "service",
                }],
            },
        }
        # Idempotence-Key = id нашего платежа: повторная инициация не создаёт дубль у провайдера.
        resp = self.client.create_payment(payload, idempotence_key=payment.id)
        crud.set_payment_provider_id(db, payment, resp["id"])
        url = (resp.get("confirmation") or {}).get("confirmation_url")
        return CheckoutResult(activated=False, payment_id=payment.id, confirmation_url=url)

    def handle_webhook(self, db: Session, event: dict) -> None:
        obj = event.get("object") or {}
        provider_payment_id = obj.get("id")
        new_status = obj.get("status")
        if not provider_payment_id:
            return
        payment = crud.get_payment_by_provider_id(db, provider_payment_id)
        if payment is None:
            return  # неизвестный платёж — игнорируем
        if new_status == "succeeded" and payment.status != "succeeded":
            crud.mark_payment(db, payment, "succeeded")
            crud.set_plan(db, payment.organization_id, payment.plan_code, status="active")
        elif new_status == "canceled" and payment.status != "canceled":
            crud.mark_payment(db, payment, "canceled")
