"""Автопродление, годовая оплата и продление от конца периода (пакет G, G5).

Обещания, которые здесь проверяются:

* **продление того же тарифа продолжает период** — досрочная оплата больше не съедает
  оставшиеся дни; другой тариф начинает период с оплаты и называет, сколько дней
  прежнего пропадёт;
* год — 12 месяцев со скидкой **владельца** (по умолчанию её нет); сумму считает сервер;
* **деньги не списываются без согласия**: отметка при оплате + способ, который провайдер
  подтвердил сохранённым; сохранённый без отметки способ ничего не включает;
* согласие — это тариф и сумма: смена тарифа его гасит, выросшая цена — останавливает;
* **без письма-предупреждения деньги не списываются**; без почты автопродления нет;
* не больше одной попытки в сутки и трёх на конец периода; «провайдер не ответил» —
  не отказ: повтора не будет, пока провайдер не назовёт итог;
* выключить можно в любой момент, и способ оплаты забывается.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import billing, crud, mail, scheduler
from app.billing import ChargeResult, PaymentProvider
from app.billing_period import (
    GRACE_DAYS,
    PERIOD_DAYS,
    RENEW_MAX_ATTEMPTS,
    lost_days,
    period_start,
    renewal_due,
)
from app.database import as_tenant
from app.db_models import AuditLogEntry, Payment
from app.main import app
from app.payments_yookassa import YooKassaPaymentProvider, charge_result
from app.plans import PLANS
from tests.test_billing_payments import FakeYooKassa

NOW = datetime(2026, 9, 20, 4, 0, tzinfo=timezone.utc)
END = NOW + timedelta(hours=12)
TEAM = PLANS["team"]


@pytest.fixture
def post(monkeypatch):
    monkeypatch.setenv("MAIL_BACKEND", "memory")
    monkeypatch.setenv("PUBLIC_URL", "https://finans.example")
    mail.clear_outbox()
    yield mail.outbox
    mail.clear_outbox()


def _org(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _journal(db, org_id: str, action: str) -> list[AuditLogEntry]:
    with as_tenant(db, org_id):
        return list(db.query(AuditLogEntry).filter(
            AuditLogEntry.organization_id == org_id, AuditLogEntry.action == action).all())


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


class Provider(PaymentProvider):
    """Провайдер, отвечающий на списания заранее заданными исходами."""

    saves_methods = True

    def __init__(self, *results: ChargeResult):
        self.results = list(results)
        self.charges: list[tuple[int, str, str]] = []

    def start_checkout(self, *args, **kwargs):
        raise AssertionError("в этих тестах оплату не оформляют")

    def charge_saved(self, db, payment, plan, method_id, customer_email):
        self.charges.append((payment.amount_rub, method_id, customer_email))
        return self.results.pop(0) if self.results else ChargeResult(status="succeeded")


def _auto(db, org_id: str, *, ends: datetime = END, amount: int = 2900, months: int = 1):
    sub = crud.set_plan(db, org_id, "team", product="business", period_end=ends, paid=True)
    return crud.enable_auto_renew(db, sub, method_id="pm-1", method_title="MasterCard *4444",
                                  months=months, amount_rub=amount)


def _warned(db) -> None:
    """Письмо за неделю до конца — то самое предупреждение о списании."""
    scheduler.send_billing_reminders(db, END - timedelta(days=6))


# --- Начало периода: чистые правила ---

def test_paying_early_for_the_same_plan_continues_the_period():
    """Найдено при проектировании: отсчёт шёл от даты платежа, и заплативший за неделю
    до конца терял семь дней."""
    end = NOW + timedelta(days=7)
    assert period_start("team", end, TEAM, NOW) == end
    assert lost_days("team", end, TEAM, NOW) == 0


def test_the_grace_period_is_paid_time_not_a_bonus():
    """В льготный срок работа шла — период продолжается от прежнего конца, иначе платить
    в последний день льготы было бы выгоднее всего."""
    ended = NOW - timedelta(days=GRACE_DAYS)
    assert period_start("team", ended, TEAM, NOW) == ended


def test_after_the_restriction_the_period_starts_from_payment():
    """Запись уже закрывалась — эти дни работой не были, и брать за них нельзя."""
    long_ago = NOW - timedelta(days=GRACE_DAYS + 1)
    assert period_start("team", long_ago, TEAM, NOW) == NOW


def test_another_plan_starts_from_payment_and_names_the_lost_days():
    end = NOW + timedelta(days=9, hours=1)
    assert period_start("business", end, TEAM, NOW) == NOW
    assert lost_days("business", end, TEAM, NOW) == 10       # неполные сутки — целые


def test_no_period_nothing_to_continue():
    assert period_start("free", None, TEAM, NOW) == NOW
    assert lost_days("free", None, TEAM, NOW) == 0


def test_early_payment_through_the_product_extends_from_the_end(client, register,
                                                                  db_session):
    headers = register()
    org_id = _org(client, headers)
    url = f"/api/v1/organizations/{org_id}/billing/checkout"
    client.post(url, json={"plan_code": "team"}, headers=headers)
    first = _aware(crud.get_subscription(db_session, org_id).current_period_end)
    client.post(url, json={"plan_code": "team"}, headers=headers)
    db_session.expire_all()
    second = _aware(crud.get_subscription(db_session, org_id).current_period_end)
    assert second == first + timedelta(days=PERIOD_DAYS)


# --- Сколько платить ---

def test_a_year_is_twelve_periods_at_the_owners_discount(client, register, monkeypatch):
    monkeypatch.setenv("ANNUAL_DISCOUNT_PERCENT", "10")
    headers = register()
    org_id = _org(client, headers)
    q = client.get(f"/api/v1/organizations/{org_id}/billing/quote",
                   params={"plan_code": "team", "months": 12}, headers=headers).json()
    assert q["full_price_rub"] == 2900 * 12
    assert q["amount_rub"] == 2900 * 12 * 90 // 100 and q["discount_percent"] == 10
    starts, ends = datetime.fromisoformat(q["starts_at"]), datetime.fromisoformat(q["ends_at"])
    assert ends - starts == timedelta(days=PERIOD_DAYS * 12)


def test_no_discount_unless_the_owner_sets_one(client):
    plans = {p["code"]: p for p in client.get("/api/v1/plans").json()}
    assert plans["team"]["annual_price_rub"] == 2900 * 12
    assert plans["team"]["annual_discount_percent"] == 0
    # Годом оплачивается только то, что оплачивается помесячно.
    assert plans["free"]["annual_price_rub"] is None
    assert plans["audit_corp"]["annual_price_rub"] is None


@pytest.mark.parametrize("raw", ["15%", "90", "-5"])
def test_a_mistyped_discount_is_not_applied_and_is_named(monkeypatch, raw):
    monkeypatch.setenv("ANNUAL_DISCOUNT_PERCENT", raw)
    assert billing.checkout_amount(TEAM, 12) == 2900 * 12
    assert "не применяется" in (billing.discount_problem() or "")


def test_the_monthly_price_never_gets_the_annual_discount(monkeypatch):
    monkeypatch.setenv("ANNUAL_DISCOUNT_PERCENT", "20")
    assert billing.checkout_amount(TEAM, 1) == 2900


def test_the_quote_names_the_days_a_plan_change_loses(client, register, db_session):
    headers = register()
    org_id = _org(client, headers)
    client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                json={"plan_code": "team"}, headers=headers)
    q = client.get(f"/api/v1/organizations/{org_id}/billing/quote",
                   params={"plan_code": "business"}, headers=headers).json()
    assert q["continues"] is False and q["lost_days"] == PERIOD_DAYS


def test_other_terms_go_through_an_invoice(client, register):
    headers = register()
    org_id = _org(client, headers)
    r = client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                    json={"plan_code": "team", "months": 3}, headers=headers)
    assert r.status_code == 422 and "по счёту" in r.json()["detail"]


# --- Согласие ---

def test_consent_turns_on_auto_renew_and_is_logged_with_its_author(client, register,
                                                                   db_session, post):
    headers = register(email="owner@e.ru")
    org_id = _org(client, headers)
    r = client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                    json={"plan_code": "team", "auto_renew": True}, headers=headers)
    assert r.status_code == 200
    sub = client.get(f"/api/v1/organizations/{org_id}/subscription", headers=headers).json()
    assert sub["auto_renew"] is True and sub["renew_amount_rub"] == 2900
    assert "без денег" in sub["payment_method_title"]       # ручной провайдер назван
    checkout = _journal(db_session, org_id, "billing.checkout")[0]
    assert checkout.actor_email == "owner@e.ru" and "согласием" in checkout.details
    assert _journal(db_session, org_id, "billing.auto_renew_on")


def test_without_mail_there_is_no_auto_renew_and_nothing_happens(client, register,
                                                                 db_session, monkeypatch):
    """Отметка, которая ни к чему не приведёт, — обещание, которое продукт не выполнит:
    без почты нет письма-предупреждения, а без него деньги не списываются."""
    monkeypatch.setenv("MAIL_BACKEND", "off")
    headers = register()
    org_id = _org(client, headers)
    sub = client.get(f"/api/v1/organizations/{org_id}/subscription", headers=headers).json()
    assert sub["auto_renew_available"] is False and "почты" in sub["auto_renew_unavailable_reason"]
    r = client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                    json={"plan_code": "team", "auto_renew": True}, headers=headers)
    assert r.status_code == 409 and "почты" in r.json()["detail"]
    assert crud.get_subscription(db_session, org_id).plan_code == "free"


@pytest.fixture
def yookassa(client):
    fake = FakeYooKassa()
    app.dependency_overrides[billing.get_payment_provider] = \
        lambda: YooKassaPaymentProvider(fake)
    yield fake
    app.dependency_overrides.pop(billing.get_payment_provider, None)


def _pay(client, org_id, headers, **extra):
    return client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                       json={"plan_code": "team", **extra}, headers=headers)


def _webhook(client, provider_id):
    return client.post("/api/v1/billing/webhook/yookassa",
                       json={"object": {"id": provider_id, "status": "succeeded"}})


CARD = {"type": "bank_card", "id": "pm-777", "saved": True,
        "card": {"last4": "4444", "card_type": "MasterCard"}}


def test_the_provider_is_asked_to_save_the_method_only_with_consent(client, register,
                                                                   yookassa, post):
    headers = register()
    org_id = _org(client, headers)
    _pay(client, org_id, headers)
    _pay(client, org_id, headers, auto_renew=True, months=12)
    without, with_consent = (c["payload"] for c in yookassa.created)
    assert "save_payment_method" not in without
    assert with_consent["save_payment_method"] is True
    assert with_consent["amount"]["value"] == f"{2900 * 12}.00"


def test_a_method_confirmed_saved_by_the_provider_turns_on_auto_renew(
        client, register, yookassa, db_session, post):
    headers = register()
    org_id = _org(client, headers)
    _pay(client, org_id, headers, auto_renew=True)
    yookassa.says("yoo-1", status="succeeded", payment_method=CARD)
    _webhook(client, "yoo-1")
    sub = client.get(f"/api/v1/organizations/{org_id}/subscription", headers=headers)
    assert sub.json()["auto_renew"] is True
    assert sub.json()["payment_method_title"] == "MasterCard *4444"
    assert "pm-777" not in sub.text                      # идентификатор наружу не уходит
    assert crud.get_subscription(db_session, org_id).payment_method_id == "pm-777"


def test_consent_without_a_saved_method_is_named_not_pretended(
        client, register, yookassa, db_session, post):
    headers = register()
    org_id = _org(client, headers)
    _pay(client, org_id, headers, auto_renew=True)
    yookassa.says("yoo-1", status="succeeded", payment_method={**CARD, "saved": False})
    _webhook(client, "yoo-1")
    sub = client.get(f"/api/v1/organizations/{org_id}/subscription", headers=headers).json()
    assert sub["plan_code"] == "team" and sub["auto_renew"] is False
    assert "не сохранил способ оплаты" in sub["renew_error"]


def test_a_saved_method_without_our_consent_enables_nothing(
        client, register, yookassa, db_session, post):
    """Способ, сохранённый провайдером без нашей отметки, — чужая настройка магазина, а
    не согласие клиента."""
    headers = register()
    org_id = _org(client, headers)
    _pay(client, org_id, headers)
    yookassa.says("yoo-1", status="succeeded", payment_method=CARD)
    _webhook(client, "yoo-1")
    sub = crud.get_subscription(db_session, org_id)
    assert sub.auto_renew is False and sub.payment_method_id is None


def test_turning_off_forgets_the_method_and_names_who(client, register, db_session, post):
    headers = register(email="owner@e.ru")
    org_id = _org(client, headers)
    _auto(db_session, org_id)
    url = f"/api/v1/organizations/{org_id}/billing/auto-renew"
    r = client.delete(url, headers=headers)
    assert r.status_code == 200 and r.json()["auto_renew"] is False
    db_session.expire_all()
    sub = crud.get_subscription(db_session, org_id)
    assert sub.payment_method_id is None and sub.renew_amount_rub == 0
    entry = _journal(db_session, org_id, "billing.auto_renew_off")[0]
    assert entry.actor_email == "owner@e.ru" and "MasterCard *4444" in entry.details
    assert client.delete(url, headers=headers).status_code == 200      # повтор безвреден
    assert len(_journal(db_session, org_id, "billing.auto_renew_off")) == 1


def test_a_plan_change_drops_consent_given_for_another_amount(client, register,
                                                              db_session, post):
    headers = register()
    org_id = _org(client, headers)
    _auto(db_session, org_id)
    client.post(f"/api/v1/organizations/{org_id}/subscription",
                json={"plan_code": "free"}, headers=headers)
    sub = crud.get_subscription(db_session, org_id)
    db_session.refresh(sub)
    assert sub.auto_renew is False and sub.payment_method_id is None
    assert "тариф сменился" in sub.renew_error
    assert "тариф сменился" in _journal(db_session, org_id, "billing.auto_renew_off")[0].details


def test_a_plan_without_a_term_has_nothing_to_renew(client, register, db_session, post):
    org_id = _org(client, register())
    sub = _auto(db_session, org_id)
    crud.set_plan(db_session, org_id, "team", product="business", period_end=None, paid=True)
    db_session.refresh(sub)
    assert sub.auto_renew is False and "нет срока" in sub.renew_error


# --- Списание ---

def test_nothing_is_charged_before_the_day(client, register, db_session, post):
    org_id = _org(client, register())
    _auto(db_session, org_id, ends=NOW + timedelta(days=3))
    provider = Provider()
    scheduler.renew_subscriptions(db_session, provider, NOW)
    assert provider.charges == []
    assert renewal_due(NOW + timedelta(days=3), NOW) is False


def test_a_warned_renewal_is_charged_and_continues_the_period(client, register,
                                                              db_session, post):
    org_id = _org(client, register(email="owner@e.ru", org="ООО «Клиент»"))
    _auto(db_session, org_id)
    _warned(db_session)
    notice = post()[0][1]
    assert "2 900 ₽" in notice.text and "MasterCard *4444" in notice.text
    assert "выключите автопродление" in notice.text
    mail.clear_outbox()

    provider = Provider()
    run = scheduler.renew_subscriptions(db_session, provider, NOW)
    assert run.charged == 1 and provider.charges == [(2900, "pm-1", "owner@e.ru")]
    db_session.expire_all()
    sub = crud.get_subscription(db_session, org_id)
    assert _aware(sub.current_period_end) == END + timedelta(days=PERIOD_DAYS)
    payment = db_session.query(Payment).filter_by(organization_id=org_id).one()
    assert payment.status == "succeeded" and _aware(payment.renews_period_end) == END
    assert "списано 2 900 ₽" in post()[0][1].subject
    assert _journal(db_session, org_id, "billing.auto_renew_charged")


def test_without_the_warning_letter_nothing_is_charged(client, register, db_session, post):
    """Деньги не списываются без письма **до** них — даже при живом согласии."""
    org_id = _org(client, register())
    _auto(db_session, org_id)
    provider = Provider()
    run = scheduler.renew_subscriptions(db_session, provider, NOW)
    assert run.not_warned == 1 and provider.charges == []
    assert "без предупреждения" in crud.get_subscription(db_session, org_id).renew_error


def test_mail_switched_off_blocks_the_charge(client, register, db_session, post,
                                             monkeypatch):
    org_id = _org(client, register())
    _auto(db_session, org_id)
    _warned(db_session)
    monkeypatch.setenv("MAIL_BACKEND", "off")
    provider = Provider()
    run = scheduler.renew_subscriptions(db_session, provider, NOW)
    assert run.blocked == 1 and provider.charges == []


def test_a_decline_is_retried_once_a_day_and_at_most_three_times(client, register,
                                                                 db_session, post):
    org_id = _org(client, register())
    _auto(db_session, org_id)
    _warned(db_session)
    mail.clear_outbox()
    declined = ChargeResult(status="failed", reason="недостаточно средств")
    provider = Provider(declined, declined, declined, declined)

    scheduler.renew_subscriptions(db_session, provider, NOW)
    assert len(provider.charges) == 1
    letter = post()[0][1]
    assert "недостаточно средств" in letter.text and "осталось попыток: 2" in letter.text
    scheduler.renew_subscriptions(db_session, provider, NOW + timedelta(hours=6))
    assert len(provider.charges) == 1                          # не чаще раза в сутки
    for day in (1, 2, 3):
        scheduler.renew_subscriptions(db_session, provider, NOW + timedelta(days=day))
    assert len(provider.charges) == RENEW_MAX_ATTEMPTS
    assert "больше не будет" in post()[-1][1].text
    sub = crud.get_subscription(db_session, org_id)
    assert sub.auto_renew is True                   # временный отказ согласия не отзывает


def test_an_unusable_card_ends_the_consent(client, register, db_session, post):
    org_id = _org(client, register())
    _auto(db_session, org_id)
    _warned(db_session)
    mail.clear_outbox()
    provider = Provider(charge_result({"id": "x", "status": "canceled",
                                       "cancellation_details": {"reason": "card_expired"}}))
    scheduler.renew_subscriptions(db_session, provider, NOW)
    sub = crud.get_subscription(db_session, org_id)
    db_session.refresh(sub)
    assert sub.auto_renew is False and sub.payment_method_id is None
    assert "срок действия карты истёк" in sub.renew_error
    assert "Автопродление выключено" in post()[0][1].text


def test_a_price_rise_stops_the_charge_instead_of_taking_more(client, register,
                                                              db_session, post):
    org_id = _org(client, register())
    sub = _auto(db_session, org_id)
    _warned(db_session)
    # Цена выросла **после** письма за неделю: поймать обязан и сам день списания.
    sub.renew_amount_rub = 2500
    db_session.commit()
    provider = Provider()
    run = scheduler.renew_subscriptions(db_session, provider, NOW)
    assert run.stopped == 1 and provider.charges == []
    assert db_session.query(Payment).filter_by(organization_id=org_id).count() == 0
    assert "цена выросла" in crud.get_subscription(db_session, org_id).renew_error


def test_a_price_rise_is_named_a_week_ahead(client, register, db_session, post):
    """Выросшую цену лучше назвать за неделю, чем в день списания."""
    org_id = _org(client, register())
    _auto(db_session, org_id, amount=2500)
    _warned(db_session)
    letter = post()[0][1]
    assert "Автопродление выключено: цена выросла" in letter.text
    assert crud.get_subscription(db_session, org_id).auto_renew is False


def test_a_pending_charge_waits_for_the_provider_and_is_not_repeated(
        client, register, db_session, post):
    org_id = _org(client, register())
    _auto(db_session, org_id)
    _warned(db_session)
    mail.clear_outbox()
    provider = Provider(ChargeResult(status="pending", provider_payment_id="p-1"))
    run = scheduler.renew_subscriptions(db_session, provider, NOW)
    assert run.pending == 1 and post() == []
    scheduler.renew_subscriptions(db_session, provider, NOW + timedelta(days=1))
    assert len(provider.charges) == 1                   # пока итога нет, второй попытки нет


def test_an_unanswered_charge_is_not_repeated_and_the_provider_settles_it(
        client, register, db_session, post, yookassa):
    """«Провайдер не ответил» — не отказ: он мог списать деньги, не успев ответить.
    Повтора нет, а пришедшее позже уведомление провайдера дописывает итог — даже когда
    его идентификатора мы так и не узнали."""
    org_id = _org(client, register())
    _auto(db_session, org_id)
    _warned(db_session)
    mail.clear_outbox()

    def no_answer(payload, idempotence_key):
        raise TimeoutError("нет ответа")

    yookassa.create_payment = no_answer
    provider = YooKassaPaymentProvider(yookassa)
    run = scheduler.renew_subscriptions(db_session, provider, NOW)
    assert run.unknown == 1
    assert "неизвестно" in post()[0][1].text
    payment = db_session.query(Payment).filter_by(organization_id=org_id).one()
    assert payment.status == "pending" and payment.provider_payment_id is None
    scheduler.renew_subscriptions(db_session, provider, NOW + timedelta(days=1))
    assert db_session.query(Payment).filter_by(organization_id=org_id).count() == 1

    yookassa.payments["yoo-late"] = {"id": "yoo-late", "status": "succeeded",
                                     "metadata": {"payment_id": payment.id}}
    r = client.post("/api/v1/billing/webhook/yookassa",
                    json={"object": {"id": "yoo-late", "metadata": {"payment_id": payment.id}}})
    assert r.status_code == 200
    db_session.expire_all()
    assert _aware(crud.get_subscription(db_session, org_id).current_period_end) \
        == END + timedelta(days=PERIOD_DAYS)


def test_a_webhook_naming_someone_elses_payment_is_ignored(client, register, db_session,
                                                           post, yookassa):
    """Метаданные тела — только подсказка: провайдер обязан сам назвать платёж нашим."""
    org_id = _org(client, register())
    _auto(db_session, org_id)
    payment = crud.create_payment(db_session, org_id, "team", 2900,
                                  renews_period_end=crud.get_subscription(
                                      db_session, org_id).current_period_end)
    yookassa.payments["yoo-x"] = {"id": "yoo-x", "status": "succeeded",
                                  "metadata": {"payment_id": "чужой"}}
    client.post("/api/v1/billing/webhook/yookassa",
                json={"object": {"id": "yoo-x", "metadata": {"payment_id": payment.id}}})
    db_session.refresh(payment)
    assert payment.status == "pending" and payment.provider_payment_id is None


def test_provider_errors_are_sorted_into_decline_and_unknown(db_session, client, register):
    org_id = _org(client, register())
    payment = crud.create_payment(db_session, org_id, "team", 2900)

    class Refused(Exception):
        response = type("R", (), {"status_code": 400})()

    class Client:
        def __init__(self, exc):
            self.exc = exc

        def create_payment(self, payload, idempotence_key):
            raise self.exc

    refused = YooKassaPaymentProvider(Client(Refused())).charge_saved(
        db_session, payment, TEAM, "pm", "a@e.ru")
    silent = YooKassaPaymentProvider(Client(ConnectionError())).charge_saved(
        db_session, payment, TEAM, "pm", "a@e.ru")
    assert refused.status == "failed" and silent.status == "unknown"


def test_every_renewal_run_leaves_a_trace(db_session):
    scheduler.renew_subscriptions(db_session, Provider(), NOW)
    assert scheduler.last_runs(db_session)["renew"] is not None
