"""Тесты платёжного флоу (6.5b): ручной провайдер и ЮKassa (через фейковый клиент).

С G5 **уведомлению не верят на слово**: состояние платежа берётся у провайдера
(`get_payment`), и фейк хранит его сам — тест говорит «провайдер считает платёж
успешным», а тело уведомления лишь называет, о каком платеже речь.
"""
import pytest

from app import crud
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

class FakeYooKassa:
    """Провайдер в памяти: что создано и что он **сам** думает о каждом платеже."""

    def __init__(self):
        self.created: list[dict] = []
        self.payments: dict[str, dict] = {}
        self.next_id = 0
        self.fail_lookup = False

    def create_payment(self, payload, idempotence_key):
        self.next_id += 1
        provider_id = f"yoo-{self.next_id}"
        self.created.append({"payload": payload, "idempotence_key": idempotence_key,
                             "id": provider_id})
        obj = {"id": provider_id, "status": "pending",
               "metadata": payload.get("metadata") or {},
               "confirmation": {"confirmation_url": "https://pay.example/x"}}
        self.payments[provider_id] = obj
        return obj

    def get_payment(self, provider_payment_id):
        if self.fail_lookup:
            raise RuntimeError("провайдер недоступен")
        return self.payments[provider_payment_id]

    def says(self, provider_payment_id, **fields):
        """Что провайдер отвечает о платеже при проверке."""
        self.payments[provider_payment_id].update(fields)


@pytest.fixture
def yookassa(client):
    fake = FakeYooKassa()
    app.dependency_overrides[get_payment_provider] = lambda: YooKassaPaymentProvider(fake)
    yield fake
    app.dependency_overrides.pop(get_payment_provider, None)


def _checkout(client, org_id, headers, **extra):
    return client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                       json={"plan_code": "team", "return_url": "https://shop/return", **extra},
                       headers=headers)


def _webhook(client, provider_id, status="succeeded"):
    return client.post("/api/v1/billing/webhook/yookassa",
                       json={"event": f"payment.{status}",
                             "object": {"id": provider_id, "status": status}})


def test_yookassa_checkout_returns_confirmation_url(client, auth_headers, yookassa):
    org_id = _org_id(client, auth_headers)
    r = _checkout(client, org_id, auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["activated"] is False
    assert body["confirmation_url"] == "https://pay.example/x"
    # 54-ФЗ чек присутствует в payload
    assert yookassa.created[0]["payload"]["receipt"]["items"][0]["amount"]["currency"] == "RUB"
    # тариф ещё не сменён (платёж в ожидании)
    assert _subscription(client, org_id, auth_headers)["plan_code"] == "free"


def test_yookassa_webhook_activates_plan(client, auth_headers, yookassa):
    org_id = _org_id(client, auth_headers)
    _checkout(client, org_id, auth_headers)
    yookassa.says("yoo-1", status="succeeded")
    assert _webhook(client, "yoo-1").status_code == 200
    assert _subscription(client, org_id, auth_headers)["plan_code"] == "team"


def test_yookassa_webhook_is_idempotent(client, auth_headers, yookassa):
    org_id = _org_id(client, auth_headers)
    _checkout(client, org_id, auth_headers)
    yookassa.says("yoo-1", status="succeeded")
    _webhook(client, "yoo-1")
    first_end = _subscription(client, org_id, auth_headers)["current_period_end"]
    _webhook(client, "yoo-1")  # повтор не ломает и **не продлевает второй раз**
    sub = _subscription(client, org_id, auth_headers)
    assert sub["plan_code"] == "team" and sub["current_period_end"] == first_end


def test_yookassa_webhook_unknown_payment_ignored(client, yookassa):
    event = {"object": {"id": "unknown-id", "status": "succeeded"}}
    assert client.post("/api/v1/billing/webhook/yookassa", json=event).status_code == 200
    assert yookassa.payments == {}


# --- Уведомлению не верят на слово (G5) ---

def test_a_webhook_claiming_success_is_checked_with_the_provider(
        client, auth_headers, yookassa):
    """Тело уведомления говорит «оплачено», провайдер — «ещё нет». Верят провайдеру:
    иначе тариф выдавал бы любой, кто знает адрес вебхука и номер платежа."""
    org_id = _org_id(client, auth_headers)
    _checkout(client, org_id, auth_headers)
    assert _webhook(client, "yoo-1", "succeeded").status_code == 200   # провайдер: pending
    assert _subscription(client, org_id, auth_headers)["plan_code"] == "free"


def test_an_unverifiable_webhook_is_refused_for_a_retry(client, auth_headers, yookassa):
    """Провайдер не ответил на проверку — 503: ЮKassa повторит уведомление сама, а
    непроверенное не обрабатывается."""
    org_id = _org_id(client, auth_headers)
    _checkout(client, org_id, auth_headers)
    yookassa.says("yoo-1", status="succeeded")
    yookassa.fail_lookup = True
    assert _webhook(client, "yoo-1").status_code == 503
    assert _subscription(client, org_id, auth_headers)["plan_code"] == "free"
    yookassa.fail_lookup = False
    assert _webhook(client, "yoo-1").status_code == 200
    assert _subscription(client, org_id, auth_headers)["plan_code"] == "team"


def test_a_canceled_payment_changes_nothing(client, auth_headers, yookassa, db_session):
    org_id = _org_id(client, auth_headers)
    _checkout(client, org_id, auth_headers)
    yookassa.says("yoo-1", status="canceled",
                  cancellation_details={"reason": "insufficient_funds"})
    _webhook(client, "yoo-1", "canceled")
    assert _subscription(client, org_id, auth_headers)["plan_code"] == "free"
    assert crud.list_payments(db_session, org_id)[0].status == "canceled"
