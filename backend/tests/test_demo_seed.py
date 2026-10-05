"""Демо-организация (пакет J, J2): заводится через маршруты, считается, укладывается в квоты.

Скрипт `scripts/seed_demo.py` — обёртка; всё, что он делает, делает `app.demo_seed.seed`,
и проверяется здесь на тестовой базе. Главное, что стережёт тест: каждый демо-проект
считается тем же маршрутом, что и экран, и его баланс сходится помесячно — демо-данные,
на которых продукт падает, хуже их отсутствия.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.demo_seed import (
    ANALYST,
    DEMO_ORG_NAME,
    FLAGSHIP_MONTHS,
    FLAGSHIP_NAME,
    OPERATOR,
    OWNER,
    RETAIL_NAME,
    SeedError,
    make_operator,
    prolong,
    seed,
)


def _login(client, account, password=None) -> dict:
    token = client.post("/api/v1/auth/login", json={
        "email": account.email, "password": password or account.password,
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded(client, db_session):
    report = seed(client, operator=lambda: make_operator(db_session, OPERATOR.password))
    return client, report


def test_every_demo_project_calculates_and_balances(seeded):
    _, report = seeded
    assert len(report.projects) == 5
    for project in report.projects:
        assert project.max_balance_gap < Decimal("1e-6"), project.name
        assert project.revenue_first_year > 0, project.name
    by_name = {p.name: p for p in report.projects}
    flagship = by_name[FLAGSHIP_NAME]
    assert flagship.months == FLAGSHIP_MONTHS
    # Проходной, но на грани проект: NPV > 0, доходность определена и выше нуля. Под
    # ним до 0.9.49 стояло «IRR не определена» — страж той находки на живой модели.
    assert flagship.npv > 0 and flagship.irr_annual is not None and flagship.irr_annual > 0
    # Действующий магазин вложения не содержит — нормы доходности не считаются, а не ноль.
    assert by_name[RETAIL_NAME].irr_annual is None


def test_accounts_log_in_with_their_roles(seeded):
    client, report = seeded
    assert [a.email for a in report.accounts] == [OWNER.email, ANALYST.email, OPERATOR.email]
    headers = _login(client, OWNER)
    orgs = client.get("/api/v1/organizations", headers=headers).json()
    assert [o["name"] for o in orgs] == [DEMO_ORG_NAME]
    members = client.get(f"/api/v1/organizations/{orgs[0]['id']}/members",
                         headers=headers).json()
    assert {m["email"]: m["role"] for m in members} == {OWNER.email: "owner",
                                                          ANALYST.email: "analyst"}
    assert client.get("/api/v1/auth/me", headers=_login(client, ANALYST)).status_code == 200
    me = client.get("/api/v1/auth/me", headers=_login(client, OPERATOR)).json()
    assert me["is_staff"] is True


def test_demo_content_is_where_the_screens_look_for_it(seeded):
    client, report = seeded
    headers = {**_login(client, OWNER), "X-Organization-Id": report.org_id}
    projects = client.get("/api/v1/projects", headers=headers).json()
    assert len(projects) == 5
    flagship = next(p for p in projects if p["name"] == FLAGSHIP_NAME)
    versions = client.get(f"/api/v1/projects/{flagship['id']}/versions", headers=headers)
    assert [v["label"] for v in versions.json()] and len(versions.json()) == 2
    comments = client.get(f"/api/v1/projects/{flagship['id']}/comments",
                          params={"anchor": "report:income"}, headers=headers).json()
    assert len(comments) == 2
    model = client.get(f"/api/v1/projects/{flagship['id']}", headers=headers).json()["model"]
    assert model["actualization"]["actual_until"] == 7          # факт — январь–август
    assert len(model["investment_plan"]["calendar"]["stages"]) == 4
    assert len(client.get("/api/v1/holdings", headers=headers).json()) == 1
    subjects = client.get("/api/v1/audit/subjects", headers=headers).json()
    assert len(subjects) == 3
    assert len(client.get("/api/v1/audit/groups", headers=headers).json()) == 1
    assert len(report.cases) == 2
    agro = next(c for c in report.cases if "Агро" in c.name)
    assert agro.verdict == "risk" and agro.risk_flags > 0   # дело-«красный флаг» им и остаётся


def test_operator_assigns_paid_tariffs(seeded):
    client, report = seeded
    headers = {**_login(client, OWNER), "X-Organization-Id": report.org_id}
    overview = client.get(f"/api/v1/organizations/{report.org_id}/overview",
                          headers=headers).json()
    plans = {p["product"]: p["plan_code"] for p in overview["products"]}
    assert plans == {"business": "team", "audit": "audit_team"}


def test_without_operator_the_demo_fits_free_quotas(client):
    """В продакшене оператор не заводится, и тариф остаётся бесплатным: демо-данные
    обязаны уложиться в его квоты, иначе скрипт упал бы на середине."""
    report = seed(client)
    assert [a.email for a in report.accounts] == [OWNER.email, ANALYST.email]
    assert report.notes and "Оператор" in report.notes[0]
    assert len(report.projects) == 5


def test_operator_password_follows_the_login_policy(db_session, client):
    with pytest.raises(SeedError):
        make_operator(db_session, "12345678")


def test_prolong_repeats_the_last_month_instead_of_zeros():
    model = {"header": {"duration_months": 3},
             "operating_plan": {"sales": [{"volume": ["10", "20", "30"], "price": ["5"] * 3}]},
             "financing": {"leases": [{"start_month": 0, "term_months": 3},
                                      {"start_month": 0, "term_months": 2}]}}
    out = prolong(model, 5)
    assert out["header"]["duration_months"] == 5
    assert out["operating_plan"]["sales"][0]["volume"] == ["10", "20", "30", "30", "30"]
    # Лизинг до конца горизонта продлевается вместе с ним; закончившийся раньше — нет.
    assert [x["term_months"] for x in out["financing"]["leases"]] == [5, 2]


def test_script_refuses_production_without_explicit_password(monkeypatch):
    from scripts.seed_demo import main

    monkeypatch.setenv("APP_ENV", "production")
    assert main([]) == 2
    assert main(["--allow-production"]) == 2
    monkeypatch.setenv("APP_ENV", "development")
    assert main(["--password", "1234"]) == 2   # политика пароля — до любой записи


def test_the_public_demo_is_seeded_flagged_and_opens_by_the_button(client, db_session):
    """Публичное демо (L2): те же данные, отдельная организация, пароли никому не
    известны — входят кнопкой. Признаки ставятся последним шагом, и после них демо
    только смотрит и считает."""
    from app import crud as crud_
    from app.access import DEMO_REFUSAL
    from app.demo_seed import PUBLIC_ORG_NAME, PUBLIC_VISITOR, seed_public

    def mark(org_id: str, email: str) -> None:
        user = crud_.get_user_by_email(db_session, email)
        crud_.mark_demo(db_session, org_id, user.id)

    report = seed_public(client, mark_demo=mark)
    assert report.org_name == PUBLIC_ORG_NAME and len(report.projects) == 5
    assert all(p.max_balance_gap < Decimal("1e-6") for p in report.projects)
    assert any("кнопкой «Посмотреть демо»" in n for n in report.notes)
    assert client.get("/api/v1/auth/capabilities").json()["demo"] is True

    token = client.post("/api/v1/auth/demo").json()["access_token"]
    visitor = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=visitor).json()["email"] == PUBLIC_VISITOR.email
    projects = client.get("/api/v1/projects", headers=visitor).json()
    assert len(projects) == 5
    pid = projects[0]["id"]
    assert client.post(f"/api/v1/projects/{pid}/calculate", headers=visitor).status_code == 200
    refused = client.delete(f"/api/v1/projects/{pid}", headers=visitor)
    assert (refused.status_code, refused.json()["detail"]) == (403, DEMO_REFUSAL)
