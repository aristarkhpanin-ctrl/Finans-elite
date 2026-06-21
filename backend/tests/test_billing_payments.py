"""Тесты платёжного флоу (6.5b): ручной провайдер и ЮKassa (через фейковый клиент)."""
import pytest

from app.billing import get_payment_provider
from app.main import app
from app.payments_yookassa import YooKassaPaymentProvider


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _subscription(client, org_id, headers) -> dict:
    return client.get(f"/api/v1/organizations/{org_id}/subscription", headers=headers).json()


# --- Ручной провайдер (по умолчанию) ---

def test_manual_checkout_activates_immediately(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    r = client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                    json={"plan_code": "team", "return_url": "https://x"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["activated"] is True
    assert _subscription(client, org_id, auth_headers)["plan_code"] == "team"


# --- ЮKassa (фейковый клиент, без сети) ---

@pytest.fixture
def yookassa(client):
    captured = {}

    class FakeClient:
        def create_payment(self, payload, idempotence_key):
            captured["payload"] = payload
            captured["idempotence_key"] = idempotence_key
            return {"id": "yoo-123", "status": "pending",
                    "confirmation": {"confirmation_url": "https://pay.example/x"}}

    app.dependency_overrides[get_payment_provider] = lambda: YooKassaPaymentProvider(FakeClient())
    yield captured
    app.dependency_overrides.pop(get_payment_provider, None)


def test_yookassa_checkout_returns_confirmation_url(client, auth_headers, yookassa):
    org_id = _org_id(client, auth_headers)
    r = client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                    json={"plan_code": "team", "return_url": "https://shop/return"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["activated"] is False
    assert body["confirmation_url"] == "https://pay.example/x"
    # 54-ФЗ чек присутствует в payload
    assert yookassa["payload"]["receipt"]["items"][0]["amount"]["currency"] == "RUB"
    # тариф ещё не сменён (платёж в ожидании)
    assert _subscription(client, org_id, auth_headers)["plan_code"] == "free"


def test_yookassa_webhook_activates_plan(client, auth_headers, yookassa):
    org_id = _org_id(client, auth_headers)
    client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                json={"plan_code": "team", "return_url": "https://shop/return"}, headers=auth_headers)
    event = {"event": "payment.succeeded", "object": {"id": "yoo-123", "status": "succeeded"}}
    assert client.post("/api/v1/billing/webhook/yookassa", json=event).status_code == 200
    assert _subscription(client, org_id, auth_headers)["plan_code"] == "team"


def test_yookassa_webhook_is_idempotent(client, auth_headers, yookassa):
    org_id = _org_id(client, auth_headers)
    client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                json={"plan_code": "team", "return_url": "https://r"}, headers=auth_headers)
    event = {"object": {"id": "yoo-123", "status": "succeeded"}}
    client.post("/api/v1/billing/webhook/yookassa", json=event)
    client.post("/api/v1/billing/webhook/yookassa", json=event)  # повтор не ломает
    assert _subscription(client, org_id, auth_headers)["plan_code"] == "team"


def test_yookassa_webhook_unknown_payment_ignored(client, yookassa):
    event = {"object": {"id": "unknown-id", "status": "succeeded"}}
    assert client.post("/api/v1/billing/webhook/yookassa", json=event).status_code == 200
