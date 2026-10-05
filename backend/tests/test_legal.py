"""Публичные документы и согласие на обработку ПД (пакет L, L5).

Главное, что держит этот файл: черновик не выдаёт себя за проверенный документ;
незаданный реквизит видно, а не пустое место; политика перечисляет то, что код
обрабатывает на самом деле; без отдельной отметки согласия регистрации нет, а время и
редакция согласия записываются.
"""
from __future__ import annotations

import pytest

from app import legal, readiness
from app.db_models import User

SELLER = {
    "SELLER_NAME": "ООО «Финанс»", "SELLER_INN": "7707083893", "SELLER_KPP": "773601001",
    "SELLER_OGRN": "1027700132195", "SELLER_ADDRESS": "Москва, ул. Тверская, 1",
    "SELLER_EMAIL": "privacy@finans.example", "SELLER_PHONE": "+7 495 000-00-00",
    "PUBLIC_URL": "https://finans.example",
}


@pytest.fixture
def no_seller(monkeypatch):
    for var in [*SELLER, "LEGAL_DOCS_EDITION"]:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def seller(no_seller):
    for var, value in SELLER.items():
        no_seller.setenv(var, value)
    return no_seller


def _text(doc: dict) -> str:
    return "\n".join(p for s in doc["sections"] for p in s["paragraphs"])


# --- Документы ---

def test_until_the_owner_approves_an_edition_every_text_is_a_draft(client, no_seller):
    index = client.get("/api/v1/legal").json()
    assert index["draft"] is True and index["edition"] == legal.DRAFT
    assert "юристом не проверен" in index["draft_note"]
    assert {d["slug"] for d in index["documents"]} == {"offer", "privacy", "consent",
                                                       "requisites"}
    for slug in ("offer", "privacy", "consent", "requisites"):
        doc = client.get(f"/api/v1/legal/{slug}").json()
        assert doc["draft"] is True and doc["draft_note"], slug


def test_an_approved_edition_drops_the_draft_mark(client, seller):
    seller.setenv("LEGAL_DOCS_EDITION", "2026-10-15")
    doc = client.get("/api/v1/legal/offer").json()
    assert doc["draft"] is False and doc["draft_note"] == ""
    assert doc["edition"] == "2026-10-15"


def test_a_missing_requisite_is_visible_not_blank(client, no_seller):
    """Пустое место в договоре читается как опечатка; пометка — как незаданное."""
    doc = client.get("/api/v1/legal/offer").json()
    assert "[не указано: ОГРН (ОГРНИП)]" in _text(doc)
    assert "[не указано: полное наименование]" in _text(doc)
    assert {"полное наименование", "ИНН", "ОГРН (ОГРНИП)", "адрес",
            "электронная почта для обращений"} <= set(doc["missing"])


def test_requisites_come_from_the_same_settings_as_invoices(client, seller):
    """Вторая копия реквизитов однажды разошлась бы со счетами."""
    doc = client.get("/api/v1/legal/requisites").json()
    text = _text(doc)
    assert "ИНН: 7707083893" in text and "ОГРН (ОГРНИП): 1027700132195" in text
    assert "Адрес сайта: https://finans.example" in text
    offer = client.get("/api/v1/legal/offer").json()
    assert "ООО «Финанс» (ИНН 7707083893, ОГРН 1027700132195)" in _text(offer)
    assert "privacy@finans.example" in _text(offer)


def test_a_sole_trader_has_no_kpp_line(client, seller):
    """У ИП КПП не бывает — пометка «не указано» была бы ложной."""
    seller.setenv("SELLER_INN", "500100732259")
    seller.delenv("SELLER_KPP")
    doc = client.get("/api/v1/legal/requisites").json()
    assert "КПП" not in _text(doc)
    assert "КПП" not in doc["missing"]


def test_the_policy_names_every_category_the_code_processes(client, seller):
    text = _text(client.get("/api/v1/legal/privacy").json())
    for category in legal.PD_CATEGORIES:
        assert category.what in text and category.purpose in text, category.what
    assert "не загружают ресурсы со сторонних серверов" in text
    assert "152-ФЗ" in text


def test_an_unknown_document_is_a_404(client):
    assert client.get("/api/v1/legal/nope").status_code == 404


# --- Согласие ---

def _register(client, **extra):
    return client.post("/api/v1/auth/register", json={
        "email": "new@legal.test", "password": "kvartal-plan-77", "full_name": "Новый",
        "organization_name": "Орг", **extra})


def test_registration_without_a_separate_consent_is_refused_with_a_reason(client,
                                                                           db_session):
    r = _register(client)
    assert r.status_code == 422 and r.json()["detail"] == legal.CONSENT_REQUIRED
    assert db_session.query(User).filter(User.email == "new@legal.test").first() is None


def test_registration_records_the_time_and_edition_of_consent(client, db_session,
                                                              no_seller):
    no_seller.setenv("LEGAL_DOCS_EDITION", "2026-10-15")
    token = _register(client, pd_consent=True).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["pd_consent_at"] and me["pd_consent_edition"] == "2026-10-15"
    user = db_session.query(User).filter(User.email == "new@legal.test").one()
    assert user.terms_accepted_at is not None and user.terms_edition == "2026-10-15"


def test_a_draft_consent_is_recorded_as_a_draft(client, db_session, no_seller):
    """Человек соглашался с черновиком — так и записано, а не «редакция неизвестна»."""
    _register(client, pd_consent=True)
    user = db_session.query(User).filter(User.email == "new@legal.test").one()
    assert user.pd_consent_edition == legal.DRAFT


def _invite(client, auth_headers, email="invited@legal.test") -> str:
    org_id = client.get("/api/v1/organizations", headers=auth_headers).json()[0]["id"]
    return client.post(f"/api/v1/organizations/{org_id}/members", headers=auth_headers,
                       json={"email": email, "role": "analyst"}).json()["invite_token"]


def test_an_invitee_gives_consent_on_activation(client, auth_headers, db_session):
    token = _invite(client, auth_headers)
    refused = client.post("/api/v1/auth/activate",
                          json={"token": token, "password": "kollega-parol7"})
    assert refused.status_code == 422 and refused.json()["detail"] == legal.CONSENT_REQUIRED
    ok = client.post("/api/v1/auth/activate",
                     json={"token": token, "password": "kollega-parol7", "pd_consent": True})
    assert ok.status_code == 200
    user = db_session.query(User).filter(User.email == "invited@legal.test").one()
    assert user.pd_consent_at is not None


def test_an_old_account_can_give_consent_from_the_profile(client, auth_headers, db_session):
    """До L5 согласие не спрашивали: это неизвестность, а не отказ."""
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    user = db_session.query(User).filter(User.email == me["email"]).one()
    user.pd_consent_at = None
    user.pd_consent_edition = ""
    db_session.commit()
    assert client.get("/api/v1/auth/me", headers=auth_headers).json()["pd_consent_at"] is None
    given = client.post("/api/v1/auth/pd-consent", headers=auth_headers).json()
    assert given["pd_consent_at"] and given["pd_consent_edition"] == legal.DRAFT


def test_the_personal_data_export_carries_the_consent(client, auth_headers):
    export = client.get("/api/v1/auth/export", headers=auth_headers).json()
    account = export["учётная_запись"]
    assert account["согласие_на_обработку_пд"] and account["редакция_согласия"]


# --- Готовность ---

def test_readiness_calls_a_draft_a_problem(no_seller):
    item = readiness._legal()
    assert item.status == readiness.PROBLEM and "черновик" in item.state
    assert "LEGAL_DOCS_EDITION" in item.how


def test_readiness_names_gaps_in_an_approved_edition(no_seller):
    no_seller.setenv("LEGAL_DOCS_EDITION", "2026-10-15")
    item = readiness._legal()
    assert item.status == readiness.PROBLEM and "SELLER_OGRN" in item.state


def test_readiness_is_ok_with_an_edition_and_full_requisites(seller):
    seller.setenv("LEGAL_DOCS_EDITION", "2026-10-15")
    item = readiness._legal()
    assert item.status == readiness.OK and "2026-10-15" in item.state


def test_a_typo_in_the_ogrn_is_named(seller):
    seller.setenv("SELLER_OGRN", "1027700132196")
    assert any("SELLER_OGRN" in p for p in legal.seller_problems())
