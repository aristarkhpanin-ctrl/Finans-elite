"""Назначение тарифа оператором платформы (ADMIN-PHASE-F, F1).

Тариф не мог выдать **никто**: клиентский маршрут менял его правом `billing.manage`
(то есть клиент выдавал его себе сам и бесплатно, да ещё и навсегда — срок не ставился),
а у оператора такого маршрута не было вовсе, и тариф «по запросу» оставался
непродаваемым.

Проверяется обещание, а не форма: оплата по счёту **начинает отсчёт** той же дверью, что
и оба провайдера, оставляет **след платежа**, попадает в **оба журнала**, а тариф без
цены срока не получает и суммы не выдумывает.
"""
from __future__ import annotations

from app import crud
from app.billing_period import PERIOD_DAYS
from app.db_models import AuditLogEntry, Payment, StaffLogEntry


def _staff(client, db_session, register, email="staff@e.ru") -> dict:
    headers = register(email=email, org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, email), is_staff=True)
    return headers


def _client_org(client, register, email="client@e.ru", org="ООО «Клиент»") -> tuple:
    headers = register(email=email, org=org)
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return headers, org_id


def _assign(client, staff, org_id, **body):
    return client.post(f"/api/v1/admin/organizations/{org_id}/subscription",
                       json=body, headers=staff)


def _sub(client, headers, org_id, product="business") -> dict:
    return client.get(f"/api/v1/organizations/{org_id}/subscription",
                      params={"product": product}, headers=headers).json()


# --- Оплата по счёту ---

def test_the_operator_assigns_a_paid_plan(client, register, db_session):
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)

    r = _assign(client, staff, org_id, plan_code="team", months=3, note="счёт № 42")
    assert r.status_code == 200

    sub = _sub(client, owner, org_id)
    assert sub["plan_code"] == "team" and sub["max_units"] == 50


def test_paying_by_invoice_starts_the_clock(client, register, db_session):
    """Тариф, который не истекает, за деньги не продают: отсчёт идёт той же дверью,
    что и у обоих провайдеров, — второй расчёт срока дал бы клиентам разные сроки за
    одни деньги."""
    from datetime import datetime, timezone

    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    _assign(client, staff, org_id, plan_code="team", months=3)

    sub = _sub(client, owner, org_id)
    assert sub["current_period_end"] is not None
    end = datetime.fromisoformat(sub["current_period_end"].replace("Z", "+00:00"))
    if end.tzinfo is None:                      # SQLite отдаёт время без пояса
        end = end.replace(tzinfo=timezone.utc)
    days = (end - datetime.now(timezone.utc)).days
    assert 3 * PERIOD_DAYS - 2 <= days <= 3 * PERIOD_DAYS


def test_the_invoice_leaves_a_payment_behind(client, register, db_session):
    """Иначе выручка по счетам не попадала бы в платежи вовсе, и «кто заплатил»
    отвечало бы только про ЮKassa."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _assign(client, staff, org_id, plan_code="team", months=3)

    payment = db_session.query(Payment).filter(
        Payment.organization_id == org_id).one()
    assert payment.provider == "manual" and payment.status == "succeeded"
    assert payment.amount_rub == 2900 * 3 and payment.plan_code == "team"


# --- Тариф без цены ---

def test_a_plan_without_a_price_gets_no_term_and_no_invented_sum(client, register,
                                                                 db_session):
    """«Корпоративный» согласуют вне продукта: тридцать дней с момента, когда оператор
    его поставил, были бы выдуманным сроком, а сумма — выдуманными деньгами."""
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)

    assert _assign(client, staff, org_id, plan_code="audit_corp").status_code == 200
    sub = _sub(client, owner, org_id, product="audit")
    assert sub["plan_code"] == "audit_corp" and sub["current_period_end"] is None
    assert db_session.query(Payment).count() == 0


def test_a_term_on_a_plan_without_a_price_is_refused_by_name(client, register,
                                                              db_session):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)

    r = _assign(client, staff, org_id, plan_code="audit_corp", months=3)
    assert r.status_code == 422 and "срок не ставится" in r.json()["detail"]


def test_zero_months_is_not_a_payment(client, register, db_session):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)

    r = _assign(client, staff, org_id, plan_code="team", months=0)
    assert r.status_code == 422 and "не оплата" in r.json()["detail"]


def test_an_unknown_plan_is_refused(client, register, db_session):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    assert _assign(client, staff, org_id, plan_code="gold").status_code == 422


def test_an_unknown_organization_is_named(client, register, db_session):
    staff = _staff(client, db_session, register)
    r = _assign(client, staff, "нет-такой", plan_code="team", months=1)
    assert r.status_code == 404


# --- Кто это видит ---

def test_the_assignment_is_written_in_both_journals(client, register, db_session):
    """Смену своего тарифа клиент обязан видеть у себя: она меняет его квоты и деньги,
    а пришла снаружи."""
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    _assign(client, staff, org_id, plan_code="team", months=2, note="счёт № 42")

    entries = client.get(f"/api/v1/organizations/{org_id}/audit-log",
                         headers=owner).json()["entries"]
    mine = next(e for e in entries if e["action"] == "staff.plan_assign")
    assert "оплачено 2 мес." in mine["details"] and "счёт № 42" in mine["details"]

    staff_actions = [e.action for e in db_session.query(StaffLogEntry).all()]
    assert "staff.plan_assign" in staff_actions


def test_only_a_platform_operator_may_assign(client, register, db_session):
    owner, org_id = _client_org(client, register)
    r = _assign(client, owner, org_id, plan_code="team", months=1)
    assert r.status_code == 403


def test_the_client_sees_the_assignment_as_their_own_plan(client, register, db_session):
    """Назначенный тариф — обычный тариф: он же в квотах, он же в ограничениях."""
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    model = client.get("/api/v1/sample").json()
    for i in range(5):                                  # предел «Бесплатного» — 5
        client.post("/api/v1/projects", json={"name": f"П{i}", "model": model},
                    headers=owner)
    assert client.post("/api/v1/projects", json={"name": "шестой", "model": model},
                       headers=owner).status_code == 402

    _assign(client, staff, org_id, plan_code="team", months=1)
    assert client.post("/api/v1/projects", json={"name": "шестой", "model": model},
                       headers=owner).status_code == 201


def test_assigning_does_not_touch_the_other_product(client, register, db_session):
    """Подписки разделены ради этого: назначение «Аудита» не переводит «Элит»."""
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    _assign(client, staff, org_id, plan_code="audit_team", months=1)

    assert _sub(client, owner, org_id, product="business")["plan_code"] == "free"
    assert _sub(client, owner, org_id, product="audit")["plan_code"] == "audit_team"


def test_the_journal_entry_survives_in_the_client_journal_verbatim(client, register,
                                                                   db_session):
    """Запись у клиента и у платформы — об одном событии, и в обеих названы тариф и срок."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _assign(client, staff, org_id, plan_code="team", months=1)

    entry = db_session.query(AuditLogEntry).filter(
        AuditLogEntry.action == "staff.plan_assign").one()
    assert entry.entity_name == "team" and "2900 ₽" in entry.details
    assert entry.actor_email == "staff@e.ru"
