"""Интеграция с ЮKassa (6.5b; автопродление — G5).

``YooKassaClient`` инкапсулирует HTTP-вызовы к API ЮKassa (в тестах подменяется фейком),
``YooKassaPaymentProvider`` реализует флоу: создать платёж → вернуть ссылку оплаты →
по уведомлению об успехе активировать тариф (идемпотентно).

**Уведомлению не верим на слово** (G5). Тело вебхука — чужие слова: его может прислать
кто угодно, знающий адрес. Состояние платежа берётся **у провайдера** повторным
запросом, и только оно решает — активировать ли тариф, сохранился ли способ оплаты,
чем кончилось автоматическое списание. До автопродления поддельный вебхук мог выдать
тариф; с ним он мог бы ещё и подложить чужой способ оплаты или выключить автопродление
«отозванным разрешением». Недоступный провайдер — 503: ЮKassa повторит уведомление
сама, а непроверенное не обрабатывается.

Обрабатывается только платёж, известный в БД: по ``provider_payment_id`` либо — если
ответа провайдера на создание мы не дождались — по нашему ``payment_id`` из метаданных,
**подтверждённых провайдером**, и только у ожидающего платежа без идентификатора.

54-ФЗ: в платёж включается чек (``receipt``) с email покупателя и позицией тарифа.
``YOOKASSA_VAT_CODE`` — код ставки НДС для чека (по умолчанию 1 — «без НДС»).
"""
from __future__ import annotations

import os

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import crud
from .billing import (
    ChargeResult,
    CheckoutResult,
    PaymentProvider,
    checkout_amount,
    settle_payment,
)
from .db_models import Payment
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

    def get_payment(self, provider_payment_id: str) -> dict:
        """Состояние платежа у провайдера — источник правды для вебхука."""
        import httpx

        resp = httpx.get(f"{self.base_url}/payments/{provider_payment_id}",
                         auth=(self.shop_id, self.secret_key), timeout=30)
        resp.raise_for_status()
        return resp.json()


#: Причины отказа ЮKassa словами (``cancellation_details.reason``). Незнакомая
#: показывается кодом — выдумать ей перевод значило бы соврать о причине.
DECLINE_REASONS: dict[str, str] = {
    "insufficient_funds": "недостаточно средств",
    "card_expired": "срок действия карты истёк",
    "permission_revoked": "разрешение на списание без подтверждения отозвано",
    "invalid_card_number": "номер карты недействителен",
    "payment_method_restricted": "операции этим способом оплаты запрещены",
    "payment_method_limit_exceeded": "превышен лимит по способу оплаты",
    "call_issuer": "банк отклонил платёж — нужно связаться с банком",
    "issuer_unavailable": "банк не ответил",
    "fraud_suspected": "платёж заблокирован из-за подозрения в мошенничестве",
    "general_decline": "банк отклонил платёж без объяснения причины",
    "3d_secure_failed": "не пройдено подтверждение платежа",
    "country_forbidden": "оплата картой этой страны недоступна",
    "internal_timeout": "провайдер не успел провести платёж",
}

#: После этих отказов способ оплаты больше не годится: повтор ничего не даст, а
#: согласие на списание им гасится.
UNUSABLE_REASONS = frozenset({"card_expired", "permission_revoked", "invalid_card_number",
                              "payment_method_restricted"})


def _receipt(customer_email: str, description: str, amount: dict) -> dict:
    return {  # 54-ФЗ
        "customer": {"email": customer_email},
        "items": [{
            "description": description,
            "quantity": "1.00",
            "amount": amount,
            "vat_code": VAT_CODE,
            "payment_mode": "full_payment",
            "payment_subject": "service",
        }],
    }


def _months_text(months: int) -> str:
    return "" if months == 1 else f", {months} мес."


def method_title(method: dict) -> str:
    """Как назвать сохранённый способ человеку: «MasterCard *4444». Без номера карты —
    её последние цифры и есть всё, что провайдер о ней сообщает."""
    card = method.get("card") or {}
    if card.get("last4"):
        return f"{card.get('card_type') or 'Карта'} *{card['last4']}"
    return str(method.get("title") or method.get("type") or "способ оплаты")


def charge_result(obj: dict) -> ChargeResult:
    """Разобрать ответ провайдера о платеже в один из четырёх исходов."""
    status = obj.get("status")
    provider_id = obj.get("id")
    if status == "succeeded":
        return ChargeResult(status="succeeded", provider_payment_id=provider_id)
    if status == "canceled":
        code = str((obj.get("cancellation_details") or {}).get("reason") or "")
        reason = DECLINE_REASONS.get(code) or (f"отказ провайдера: {code}" if code
                                              else "провайдер отменил платёж")
        return ChargeResult(status="failed", provider_payment_id=provider_id, reason=reason,
                            method_unusable=code in UNUSABLE_REASONS)
    return ChargeResult(status="pending", provider_payment_id=provider_id)


class YooKassaPaymentProvider(PaymentProvider):
    saves_methods = True

    def __init__(self, client: YooKassaClient):
        self.client = client

    def start_checkout(self, db: Session, org_id: str, plan: Plan, return_url: str,
                       customer_email: str, *, months: int = 1,
                       auto_renew: bool = False) -> CheckoutResult:
        amount_rub = checkout_amount(plan, months)
        payment = crud.create_payment(db, org_id, plan.code, amount_rub, provider="yookassa",
                                      months=months, auto_renew_consent=auto_renew)
        amount = {"value": f"{amount_rub}.00", "currency": "RUB"}
        payload = {
            "amount": amount,
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": f"Тариф «{plan.name}»{_months_text(months)}",
            "metadata": {"organization_id": org_id, "plan_code": plan.code,
                         "payment_id": payment.id},
            "receipt": _receipt(customer_email,
                                f"Подписка: тариф «{plan.name}»{_months_text(months)}", amount),
        }
        if auto_renew:
            # Просьба сохранить способ — только по отметке согласия. Сохранится ли он,
            # решает провайдер (не всякий способ сохраняем); ответ придёт с оплатой.
            payload["save_payment_method"] = True
        # Idempotence-Key = id нашего платежа: повторная инициация не создаёт дубль у провайдера.
        resp = self.client.create_payment(payload, idempotence_key=payment.id)
        crud.set_payment_provider_id(db, payment, resp["id"])
        url = (resp.get("confirmation") or {}).get("confirmation_url")
        return CheckoutResult(activated=False, payment_id=payment.id, confirmation_url=url)

    def charge_saved(self, db: Session, payment: Payment, plan: Plan, method_id: str,
                     customer_email: str) -> ChargeResult:
        """Списать сохранённым способом. Ответ «провайдер не ответил» — не отказ.

        Отказ по запросу (4xx) значит, что платёж не создан, — это ``failed``. Всё
        остальное (5xx, обрыв связи, таймаут) — ``unknown``: провайдер мог списать
        деньги, не успев ответить, и повтор взял бы их дважды. Такое списание ждёт
        уведомления провайдера, а не следующей попытки.
        """
        amount = {"value": f"{payment.amount_rub}.00", "currency": "RUB"}
        description = f"Автопродление: тариф «{plan.name}»{_months_text(payment.months)}"
        payload = {
            "amount": amount,
            "capture": True,
            "payment_method_id": method_id,
            "description": description,
            "metadata": {"organization_id": payment.organization_id,
                         "plan_code": plan.code, "payment_id": payment.id},
            "receipt": _receipt(customer_email, description, amount),
        }
        try:
            resp = self.client.create_payment(payload, idempotence_key=payment.id)
        except Exception as exc:  # noqa: BLE001 — исход разбирается по ответу, см. выше
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if isinstance(code, int) and 400 <= code < 500:
                return ChargeResult(status="failed",
                                    reason=f"провайдер отклонил запрос (код {code})")
            return ChargeResult(status="unknown", reason="провайдер не ответил")
        if resp.get("id"):
            crud.set_payment_provider_id(db, payment, resp["id"])
        return charge_result(resp)

    def _verified(self, provider_payment_id: str) -> dict:
        try:
            return self.client.get_payment(provider_payment_id)
        except Exception as exc:  # noqa: BLE001 — любая неудача проверки = не обрабатывать
            raise HTTPException(
                status_code=503,
                detail="Провайдер не подтвердил состояние платежа — уведомление будет "
                       "обработано при повторе") from exc

    def _find(self, db: Session, obj: dict) -> Payment | None:
        """Наш платёж по уведомлению. Без идентификатора у нас — только ожидающий, и
        только если метаданные назвали его; окончательно решает ответ провайдера."""
        payment = crud.get_payment_by_provider_id(db, obj["id"])
        if payment is not None:
            return payment
        ours = (obj.get("metadata") or {}).get("payment_id")
        candidate = crud.get_payment(db, str(ours)) if ours else None
        if (candidate is None or candidate.provider_payment_id is not None
                or candidate.status != "pending"):
            return None
        return candidate

    def handle_webhook(self, db: Session, event: dict) -> None:
        obj = event.get("object") or {}
        if not obj.get("id"):
            return
        payment = self._find(db, obj)
        if payment is None:
            return  # неизвестный платёж — игнорируем
        fresh = self._verified(obj["id"])
        if payment.provider_payment_id is None:
            # Платёж без нашего ответа от провайдера: принимается, только если провайдер
            # сам называет его нашим.
            if (fresh.get("metadata") or {}).get("payment_id") != payment.id:
                return
            crud.set_payment_provider_id(db, payment, obj["id"])
        result = charge_result(fresh)
        if result.status == "pending" or payment.status != "pending":
            return  # итога ещё нет, либо он уже записан — повтор не ломает
        # Импорт здесь: модуль провайдера загружается при сборке `billing.provider`.
        from . import scheduler
        if payment.renews_period_end is not None:
            scheduler.settle_renewal(db, payment, result)
            return
        if result.status == "succeeded":
            method = fresh.get("payment_method") or {}
            # Способ сохранён, только если это сказал **провайдер** — в проверенном
            # ответе, а не в теле уведомления.
            saved_id = str(method["id"]) if method.get("saved") and method.get("id") else None
            settle_payment(db, payment, saved_method_id=saved_id,
                           saved_method_title=method_title(method))
        else:
            crud.mark_payment(db, payment, "canceled")
