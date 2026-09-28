"""Выбор платёжного провайдера: в продакшене тариф не выдаётся даром (пакет G, G1).

Ручной провайдер включает тариф **сразу и без денег** — ради разработки и тестов. Он
выбирался всякий раз, когда не заданы ключи ЮKassa, **при любом окружении**, и в
продакшене ``checkout`` отдавал платный тариф одним запросом. Та же дыра, что закрыл F1
на прямой смене тарифа, только через другую дверь.

Проверяется обещание целиком: не только «вернулась ошибка», но и что ничего не
случилось — тариф прежний, платёж не заведён, — и что отказ называет выход.
"""
from __future__ import annotations

import pytest

from app import crud
from app.billing import (
    PAYMENT_UNAVAILABLE,
    ManualPaymentProvider,
    UnavailablePaymentProvider,
    _build_provider,
    get_payment_provider,
    provider_kind,
)
from app.main import app
from app.payments_yookassa import YooKassaPaymentProvider


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


# --- Выбор по окружению ---

@pytest.mark.parametrize("env", ["production", "PRODUCTION", " production "])
def test_production_without_keys_refuses_instead_of_giving_plans_away(env):
    assert isinstance(_build_provider(app_env=env, shop_id="", secret=""),
                      UnavailablePaymentProvider)


def test_outside_production_the_manual_provider_stays():
    # Разработке и тестам ручной провайдер нужен: без него оплату не проверить вовсе.
    assert isinstance(_build_provider(app_env="development", shop_id="", secret=""),
                      ManualPaymentProvider)


def test_keys_win_in_any_environment():
    for env in ("production", "development"):
        assert isinstance(_build_provider(app_env=env, shop_id="shop", secret="key"),
                          YooKassaPaymentProvider)


def test_half_a_key_is_not_a_key():
    # Одна переменная из двух — это забытая настройка, а не подключённая оплата.
    assert isinstance(_build_provider(app_env="production", shop_id="shop", secret=""),
                      UnavailablePaymentProvider)


def test_provider_kind_names_all_three():
    assert provider_kind(UnavailablePaymentProvider()) == "unavailable"
    assert provider_kind(ManualPaymentProvider()) == "manual"
    assert provider_kind(_build_provider(app_env="x", shop_id="a", secret="b")) == "yookassa"


# --- Отказ на маршруте ---

@pytest.fixture
def unavailable(client):
    app.dependency_overrides[get_payment_provider] = lambda: UnavailablePaymentProvider()
    yield
    app.dependency_overrides.pop(get_payment_provider, None)


def test_checkout_refuses_and_nothing_happens(client, auth_headers, db_session, unavailable):
    """Отказ — не только код ответа: тариф прежний, платёж не заведён, журнал молчит."""
    org_id = _org_id(client, auth_headers)
    r = client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                    json={"plan_code": "team", "return_url": "https://x"},
                    headers=auth_headers)

    assert r.status_code == 503
    assert crud.get_subscription(db_session, org_id, "business").plan_code == "free"
    assert crud.count_payments(db_session, org_id) == 0
    actions = [e["action"] for e in client.get(
        f"/api/v1/organizations/{org_id}/audit-log", headers=auth_headers).json()["entries"]]
    assert "billing.checkout" not in actions


def test_the_refusal_names_the_way_out(client, auth_headers, unavailable):
    # Клиент, готовый платить, не должен упереться в «ошибку»: оплата по счёту работает.
    org_id = _org_id(client, auth_headers)
    r = client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                    json={"plan_code": "team", "return_url": "https://x"},
                    headers=auth_headers)
    assert r.json()["detail"] == PAYMENT_UNAVAILABLE
    assert "по счёту" in PAYMENT_UNAVAILABLE
