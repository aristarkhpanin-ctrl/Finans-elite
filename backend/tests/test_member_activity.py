"""Видимость активности участников (ADMIN-DECOMPOSITION.md, фаза A3).

Администратор не мог ответить на простой вопрос: кто вообще пользуется организацией.
Списка входов не было, а «последний раз заходил» неоткуда было взять — значит и отозвать
доступ у того, кто полгода не появлялся, было не на чем.

Отметка ставится в той же проходной точке членства, что и проверка блокировки: другого
места, через которое гарантированно проходит работа с организацией, нет. Проверяется,
что она **ставится**, что не пишется на каждый запрос (иначе таблица членства станет
счётчиком обращений) и что «неизвестно» не выдаётся за «никогда».
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import crud
from app.deps import SEEN_INTERVAL


def _members(client, headers) -> tuple[str, str]:
    org = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return org, f"/api/v1/organizations/{org}/members"


def _me(client, headers, url) -> dict:
    email = client.get("/api/v1/auth/me", headers=headers).json()["email"]
    return next(m for m in client.get(url, headers=headers).json() if m["email"] == email)


def test_presence_is_recorded_on_work_with_the_organization(client, auth_headers):
    org, url = _members(client, auth_headers)
    client.get("/api/v1/projects", headers=auth_headers)
    assert _me(client, auth_headers, url)["last_seen_at"] is not None


def test_presence_is_not_written_on_every_request(client, auth_headers, db_session):
    """Отметка на каждый запрос превратила бы членство в счётчик обращений."""
    org, url = _members(client, auth_headers)
    client.get("/api/v1/projects", headers=auth_headers)
    first = _me(client, auth_headers, url)["last_seen_at"]

    for _ in range(5):
        client.get("/api/v1/projects", headers=auth_headers)
    assert _me(client, auth_headers, url)["last_seen_at"] == first


def test_presence_refreshes_after_the_interval(client, auth_headers, db_session):
    org, url = _members(client, auth_headers)
    client.get("/api/v1/projects", headers=auth_headers)
    user_id = client.get("/api/v1/auth/me", headers=auth_headers).json()["id"]

    # Отматываем отметку назад — как если бы человек не заходил дольше интервала.
    membership = crud.get_membership(db_session, org, user_id)
    stale = datetime.now(timezone.utc) - SEEN_INTERVAL - timedelta(minutes=1)
    membership.last_seen_at = stale
    db_session.commit()

    client.get("/api/v1/projects", headers=auth_headers)
    fresh = _me(client, auth_headers, url)["last_seen_at"]
    assert datetime.fromisoformat(fresh).replace(tzinfo=timezone.utc) > stale


def test_never_seen_is_unknown_not_never(client, auth_headers):
    """Приглашённый, ещё не входивший, — «неизвестно», а не «никогда не работал»."""
    org, url = _members(client, auth_headers)
    client.post(url, json={"email": "новый@e.ru", "full_name": "Новый", "role": "editor"},
                headers=auth_headers)
    row = next(m for m in client.get(url, headers=auth_headers).json()
               if m["email"] == "новый@e.ru")
    assert row["last_seen_at"] is None


def test_presence_belongs_to_the_organization_not_to_the_person(client, auth_headers,
                                                                register):
    """Работа в одной организации не выдаётся за присутствие в другой: администратор
    второй увидел бы «заходил вчера» о человеке, который к нему не заглядывал."""
    other = register(email="вторая@e.ru", org="Вторая")
    org_a, url_a = _members(client, auth_headers)
    org_b, url_b = _members(client, other)

    # Один и тот же человек — участник обеих организаций.
    client.post(url_a, json={"email": "общий@e.ru", "full_name": "Общий", "role": "editor"},
                headers=auth_headers)
    member = client.post(url_b, json={"email": "общий@e.ru", "full_name": "Общий",
                                      "role": "editor"}, headers=other).json()
    client.post("/api/v1/auth/activate",
                json={"token": member["invite_token"], "password": "secret123"})
    worker = {"Authorization": "Bearer " + client.post(
        "/api/v1/auth/login",
        json={"email": "общий@e.ru", "password": "secret123"}).json()["access_token"]}

    # Работает только во второй организации.
    client.get("/api/v1/projects", headers={**worker, "X-Organization-Id": org_b})

    in_a = next(m for m in client.get(url_a, headers=auth_headers).json()
                if m["email"] == "общий@e.ru")
    in_b = next(m for m in client.get(url_b, headers=other).json()
                if m["email"] == "общий@e.ru")
    assert in_a["last_seen_at"] is None        # к первой организации не обращался
    assert in_b["last_seen_at"] is not None


def test_blocked_member_does_not_get_a_fresh_mark(client, auth_headers):
    """Отказ — не работа: иначе приостановленный выглядел бы активным ровно потому,
    что стучится в закрытую дверь."""
    org, url = _members(client, auth_headers)
    member = client.post(url, json={"email": "к@e.ru", "full_name": "К", "role": "editor"},
                         headers=auth_headers).json()
    client.post("/api/v1/auth/activate",
                json={"token": member["invite_token"], "password": "secret123"})
    worker = {"Authorization": "Bearer " + client.post(
        "/api/v1/auth/login",
        json={"email": "к@e.ru", "password": "secret123"}).json()["access_token"]}
    client.get("/api/v1/projects", headers=worker)
    before = next(m for m in client.get(url, headers=auth_headers).json()
                  if m["email"] == "к@e.ru")["last_seen_at"]

    client.post(f"{url}/{member['user_id']}/block", json={"reason": "увольнение"},
                headers=auth_headers)
    for _ in range(3):
        assert client.get("/api/v1/projects", headers=worker).status_code == 403

    after = next(m for m in client.get(url, headers=auth_headers).json()
                 if m["email"] == "к@e.ru")["last_seen_at"]
    assert after == before


def test_presence_survives_role_change(client, auth_headers):
    """Отметка живёт на членстве, а не пересоздаётся вместе с ролью."""
    org, url = _members(client, auth_headers)
    client.get("/api/v1/projects", headers=auth_headers)
    seen = _me(client, auth_headers, url)["last_seen_at"]
    member = client.post(url, json={"email": "к@e.ru", "full_name": "К", "role": "editor"},
                         headers=auth_headers).json()
    client.patch(f"{url}/{member['user_id']}", json={"role": "viewer"}, headers=auth_headers)
    assert _me(client, auth_headers, url)["last_seen_at"] == seen
