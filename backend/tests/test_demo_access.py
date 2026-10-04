"""Демо без регистрации (пакет L, L2).

Демо-вход общий: им входит каждый посетитель сайта. Поэтому проверяется прежде всего то,
что **один посетитель не может оставить следа для следующего**: ни в данных, ни в учётной
записи, ни в списке входов. Закрытость — по умолчанию: каждый изменяющий маршрут
приложения отказывает демо-входу, кроме перечня расчётов, и это сверяется с самими
маршрутами, а не с памятью.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import crud, metrics, ratelimit, readiness, usage
from app.access import DEMO_REASON, DEMO_REFUSAL
from app.billing import ManualPaymentProvider
from app.db_models import UsageEvent, UserSession
from app.deps import DEMO_ALLOWED, DEMO_CALC_LIMIT
from app.main import app
from app.metrics import TenantTotals
from app.routers.auth import DEMO_EXPORT_REFUSED, DEMO_TTL_SECONDS, DEMO_UNAVAILABLE

#: Изменяющие маршруты, которые демо-шлюз не видит, потому что за ними нет вошедшего
#: человека, — с причиной. Всё остальное обязано отказывать демо-входу.
PUBLIC: dict[str, str] = {
    "POST /api/v1/auth/register": "регистрация — до входа",
    "POST /api/v1/auth/login": "вход по паролю",
    "POST /api/v1/auth/activate": "ссылка приглашения или сброса",
    "POST /api/v1/auth/forgot-password": "просьба о ссылке — до входа",
    "POST /api/v1/auth/verify-email": "ссылка из письма, без входа",
    "POST /api/v1/auth/demo": "сам демо-вход",
    "POST /api/v1/billing/webhook/yookassa": "уведомление провайдера",
    "POST /api/v1/client-errors": "ошибка интерфейса, без пользователя",
    "POST /api/v1/comments/unsubscribe": "отписка по ссылке из письма, без входа",
}


def _mutating_routes() -> set[str]:
    out = set()
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
                out.add(f"{method.upper()} {path}")
    return out


@pytest.fixture
def demo(client, register, db_session):
    """Маленькое демо: организация с проектом и общий вход-наблюдатель."""
    owner = register("owner@demo.test", "Демо-организация")
    org_id = client.get("/api/v1/organizations", headers=owner).json()[0]["id"]
    model = client.get("/api/v1/sample").json()
    project_id = client.post("/api/v1/projects", headers=owner,
                             json={"name": "Демо-проект", "model": model}).json()["id"]
    invite = client.post(f"/api/v1/organizations/{org_id}/members", headers=owner, json={
        "email": "visitor@demo.test", "full_name": "Посетитель", "role": "viewer"}).json()
    client.post("/api/v1/auth/activate", json={
        "token": invite["invite_token"], "password": "Posetitel-Demo-2026",
        "full_name": "Посетитель"})
    visitor = crud.get_user_by_email(db_session, "visitor@demo.test")
    crud.mark_demo(db_session, org_id, visitor.id)
    token = client.post("/api/v1/auth/demo").json()["access_token"]
    return SimpleNamespace(owner=owner, org_id=org_id, project_id=project_id,
                           visitor={"Authorization": f"Bearer {token}"}, user_id=visitor.id)


def test_without_a_demo_there_is_no_button_and_the_door_says_why(client):
    assert client.get("/api/v1/auth/capabilities").json()["demo"] is False
    r = client.post("/api/v1/auth/demo")
    assert r.status_code == 404 and r.json()["detail"] == DEMO_UNAVAILABLE


def test_the_demo_door_opens_a_short_session(client, demo, db_session):
    assert client.get("/api/v1/auth/capabilities").json()["demo"] is True
    me = client.get("/api/v1/auth/me", headers=demo.visitor).json()
    assert me["is_demo"] is True and me["email"] == "visitor@demo.test"
    # Свежий сверху — демо-сеанс (у входа по ссылке активации, заведшей посетителя, свой).
    session = crud.list_sessions(db_session, demo.user_id)[0]
    left = session.expires_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(0) < left <= timedelta(seconds=DEMO_TTL_SECONDS)


def test_the_demo_reads_and_calculates(client, demo):
    projects = client.get("/api/v1/projects", headers=demo.visitor)
    assert projects.status_code == 200 and projects.json()[0]["name"] == "Демо-проект"
    calc = client.post(f"/api/v1/projects/{demo.project_id}/calculate", headers=demo.visitor)
    assert calc.status_code == 200 and calc.json()["n"] > 0
    what_if = client.post(f"/api/v1/projects/{demo.project_id}/what-if",
                          headers=demo.visitor, json={})
    assert what_if.status_code != 403


def test_every_mutating_route_refuses_the_demo_unless_it_is_a_calculation(client, demo):
    """Закрыто по умолчанию: маршрут, о демо не подумавший, отказывает сам — и ровно
    той причиной, которую посетитель поймёт."""
    leaks = []
    for key in sorted(_mutating_routes() - set(DEMO_ALLOWED) - set(PUBLIC)):
        method, path = key.split(" ", 1)
        r = client.request(method, re.sub(r"\{[^}]+\}", "x", path),
                           headers=demo.visitor, json={})
        if not (r.status_code == 403 and r.json().get("detail") == DEMO_REFUSAL):
            leaks.append(f"{key} → {r.status_code} {r.text[:80]}")
    assert not leaks, "демо-вход прошёл туда, где меняют:\n" + "\n".join(leaks)


def test_the_lists_name_only_real_routes():
    live = _mutating_routes()
    assert not set(DEMO_ALLOWED) - live, "в DEMO_ALLOWED маршрут, которого нет"
    assert not set(PUBLIC) - live, "в PUBLIC маршрут, которого нет"
    assert not set(DEMO_ALLOWED) & set(PUBLIC)


def test_the_demo_cannot_touch_its_account(client, demo):
    """Учётную запись делят все посетители: пароль, второй фактор, «выйти везде» и
    удаление одного посетителя заперли бы демо для всех остальных."""
    for method, path, body in (
            ("PATCH", "/api/v1/auth/me", {"full_name": "Взломщик"}),
            ("POST", "/api/v1/auth/password", {"current_password": "x", "new_password": "y"}),
            ("POST", "/api/v1/auth/totp/setup", {}),
            ("POST", "/api/v1/auth/sessions/revoke-all", {}),
            ("POST", "/api/v1/auth/delete", {"password": "x"}),
            ("POST", "/api/v1/organizations", {"name": "Своя"})):
        r = client.request(method, path, headers=demo.visitor, json=body)
        assert (r.status_code, r.json()["detail"]) == (403, DEMO_REFUSAL), path


def test_other_visitors_sessions_are_not_shown(client, demo):
    second = client.post("/api/v1/auth/demo").json()["access_token"]
    mine = client.get("/api/v1/auth/sessions",
                      headers={"Authorization": f"Bearer {second}"}).json()
    assert len(mine) == 1 and mine[0]["current"] is True


def test_the_demo_cannot_export_the_shared_account(client, demo):
    r = client.get("/api/v1/auth/export", headers=demo.visitor)
    assert (r.status_code, r.json()["detail"]) == (403, DEMO_EXPORT_REFUSED)


def test_the_demo_organization_is_read_only_for_everyone(client, demo):
    """Даже владелец демо-организации её не правит: следующий посетитель увидел бы
    правки. Причина — та же, что на баннере."""
    model = client.get("/api/v1/sample").json()
    r = client.put(f"/api/v1/projects/{demo.project_id}", headers=demo.owner,
                   json={"model": model})
    assert r.status_code == 403 and DEMO_REASON in r.json()["detail"]
    org = client.get("/api/v1/organizations", headers=demo.visitor).json()[0]
    kinds = {(x["product"], x["kind"], x["blocking"]) for x in org["restrictions"]}
    assert ("business", "demo", True) in kinds and ("audit", "demo", True) in kinds


def test_calculations_have_a_ceiling(client, demo, monkeypatch):
    """Расчёты открыты, но общий вход — не бесплатная вычислительная ферма."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    ratelimit._store.clear()
    url = f"/api/v1/projects/{demo.project_id}/calculate"
    for _ in range(DEMO_CALC_LIMIT):
        assert client.post(url, headers=demo.visitor).status_code == 200
    refused = client.post(url, headers=demo.visitor)
    assert refused.status_code == 429 and "зарегистрируйтесь" in refused.json()["detail"]
    ratelimit._store.clear()


def test_expired_demo_sessions_are_swept_on_the_next_visit(client, demo, db_session):
    for s in db_session.query(UserSession).filter(UserSession.user_id == demo.user_id):
        s.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    client.post("/api/v1/auth/demo")
    db_session.expire_all()
    rows = db_session.query(UserSession).filter(UserSession.user_id == demo.user_id).all()
    assert len(rows) == 1 and rows[0].revoked_at is None


def test_visitors_are_not_counted_as_customers(client, demo, register, db_session,
                                               monkeypatch):
    """События демо не пишутся, а сводка платформы демо не считает — иначе посетители
    сайта выглядели бы самой активной организацией."""
    monkeypatch.setenv("USAGE_EVENTS", "1")
    client.post(f"/api/v1/projects/{demo.project_id}/calculate", headers=demo.visitor)
    db_session.expire_all()
    assert db_session.query(UsageEvent).filter(
        UsageEvent.organization_id == demo.org_id).count() == 0
    assert usage.record(db_session, event="project.calculate", org_id=demo.org_id) is None

    register("client@real.test", "Настоящий клиент")
    report = metrics.build_platform_metrics(db_session, totals=TenantTotals())
    assert report.organizations == 1                    # только настоящий клиент
    assert report.users == 1
    assert any("Демо-организации (1)" in note for note in report.notes)


def test_readiness_names_the_demo(client, db_session, demo):
    items = {i.key: i for i in readiness.check(db_session, provider=ManualPaymentProvider())}
    assert items["demo"].status == "ok" and "Демо-организация" in items["demo"].state


def test_readiness_without_a_demo_is_off_not_a_problem(client, db_session):
    items = {i.key: i for i in readiness.check(db_session, provider=ManualPaymentProvider())}
    assert items["demo"].status == "off" and "--public" in items["demo"].how
