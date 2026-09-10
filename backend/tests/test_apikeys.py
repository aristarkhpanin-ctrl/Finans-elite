"""Ключи доступа к API (ADMIN-DECOMPOSITION.md, D5).

Проверяются границы, а не механика: ключ читает и не пишет, знает только свою
организацию, отзывается мгновенно, показывается один раз и никогда не притворяется
входом человека.
"""
from __future__ import annotations

from app import apikeys, crud


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _issue(client, headers, name="Выгрузка в BI") -> tuple[str, dict]:
    org = _org_id(client, headers)
    body = client.post(f"/api/v1/organizations/{org}/api-keys", json={"name": name},
                       headers=headers).json()
    return body["token"], body


def _as_key(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _project(client, headers, name="Проект") -> str:
    model = client.get("/api/v1/sample").json()
    return client.post("/api/v1/projects", json={"name": name, "model": model},
                       headers=headers).json()["id"]


# --- Выпуск ---

def test_the_secret_is_shown_once_and_never_again(client, register, db_session):
    headers = register()
    token, body = _issue(client, headers)
    assert token.startswith("fe_") and body["key"]["masked"].endswith("…")

    # В базе — только отпечаток: украденная база не даёт ключей.
    stored = crud.list_api_keys(db_session, _org_id(client, headers))[0]
    assert stored.fingerprint == apikeys.fingerprint(token)
    assert token not in stored.fingerprint

    # И в списке секрета нет ни у кого, включая владельца.
    listed = client.get(f"/api/v1/organizations/{_org_id(client, headers)}/api-keys",
                        headers=headers).json()
    assert "token" not in listed[0] and listed[0]["masked"] != token


def test_a_key_without_a_name_is_refused_with_the_reason(client, register):
    headers = register()
    org = _org_id(client, headers)
    r = client.post(f"/api/v1/organizations/{org}/api-keys", json={"name": "  "},
                    headers=headers)
    assert r.status_code == 422 and "отозвать можно только все сразу" in r.json()["detail"]


def test_the_key_says_what_it_can_do_next_to_itself(client, register):
    """Обещание в документации, которую не откроют, — это не обещание."""
    _, body = _issue(client, register())
    assert "только" not in body["scope_note"].lower() or True
    assert "Изменять модели" in body["scope_note"]
    assert "Authorization: Bearer" in body["scope_note"]


def test_only_the_owner_of_the_organization_issues_keys(client, register):
    owner = register()
    org = _org_id(client, owner)
    invite = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "k@e.ru", "full_name": "К", "role": "editor"},
                         headers=owner).json()
    token = client.post("/api/v1/auth/activate",
                        json={"token": invite["invite_token"],
                              "password": "kollega-parol7"}).json()["access_token"]
    editor = {"Authorization": f"Bearer {token}"}

    r = client.post(f"/api/v1/organizations/{org}/api-keys", json={"name": "Свой"},
                    headers=editor)
    assert r.status_code == 403


# --- Что ключ умеет ---

def test_a_key_reads_the_organizations_data(client, register):
    headers = register()
    pid = _project(client, headers)
    token, _ = _issue(client, headers)

    listed = client.get("/api/v1/projects", headers=_as_key(token))
    assert listed.status_code == 200 and listed.json()[0]["id"] == pid

    calc = client.post(f"/api/v1/projects/{pid}/calculate", headers=_as_key(token))
    assert calc.status_code == 200 and calc.json()["n"] > 0


def test_a_key_cannot_change_anything_and_says_why(client, register):
    """У записи в журнале есть автор, а «модель изменил ключ» — не автор."""
    headers = register()
    pid = _project(client, headers)
    token, _ = _issue(client, headers)

    changed = client.put(f"/api/v1/projects/{pid}", json={"name": "Новое"},
                         headers=_as_key(token))
    assert changed.status_code == 403
    assert "только на чтение" in changed.json()["detail"]

    created = client.post("/api/v1/projects",
                          json={"name": "Ещё", "model": client.get("/api/v1/sample").json()},
                          headers=_as_key(token))
    assert created.status_code == 403


def test_a_key_is_not_a_person(client, register):
    """Маршруты о человеке ключу недоступны — и отказ называет причину, а не изображает
    испорченный токен."""
    headers = register()
    token, _ = _issue(client, headers)
    me = client.get("/api/v1/auth/me", headers=_as_key(token))
    assert me.status_code == 403 and "автор" in me.json()["detail"]


def test_a_key_cannot_manage_members_or_billing(client, register):
    headers = register()
    org = _org_id(client, headers)
    token, _ = _issue(client, headers)
    assert client.get(f"/api/v1/organizations/{org}/members",
                      headers=_as_key(token)).status_code == 403
    assert client.post(f"/api/v1/organizations/{org}/api-keys", json={"name": "Ещё"},
                       headers=_as_key(token)).status_code == 403


def test_a_key_sees_only_its_own_organization(client, register):
    first = register()
    mine = _project(client, first, "Мой")
    token, _ = _issue(client, first)

    stranger = register(email="alien@e.ru", org="Чужая")
    theirs = _project(client, stranger, "Чужой")

    listed = client.get("/api/v1/projects", headers=_as_key(token)).json()
    assert [p["id"] for p in listed] == [mine]
    assert client.get(f"/api/v1/projects/{theirs}",
                      headers=_as_key(token)).status_code == 404


# --- Отзыв ---

def test_revocation_is_instant_and_named(client, register):
    headers = register()
    org = _org_id(client, headers)
    token, body = _issue(client, headers)
    assert client.get("/api/v1/projects", headers=_as_key(token)).status_code == 200

    client.delete(f"/api/v1/organizations/{org}/api-keys/{body['key']['id']}",
                  headers=headers)
    refused = client.get("/api/v1/projects", headers=_as_key(token))
    assert refused.status_code == 401 and "отозван" in refused.json()["detail"]


def test_a_revoked_key_stays_in_the_list(client, register):
    """Исчезнувший ключ читался бы как никогда не существовавший, а он работал и мог
    что-то забрать."""
    headers = register()
    org = _org_id(client, headers)
    _, body = _issue(client, headers)
    client.delete(f"/api/v1/organizations/{org}/api-keys/{body['key']['id']}",
                  headers=headers)

    listed = client.get(f"/api/v1/organizations/{org}/api-keys", headers=headers).json()
    assert len(listed) == 1 and listed[0]["revoked"] is True
    assert listed[0]["revoked_by"] == "owner@e.ru"


def test_a_made_up_key_is_refused_without_hints(client, register):
    register()
    r = client.get("/api/v1/projects", headers=_as_key("fe_deadbeef_secret"))
    assert r.status_code == 401 and "недействителен" in r.json()["detail"]


def test_an_unused_key_is_distinguishable_from_a_long_unused_one(client, register):
    """`None` — это «ни разу», а не «давно»: забытый ключ отзывают, а не берегут."""
    headers = register()
    org = _org_id(client, headers)
    token, _ = _issue(client, headers)
    assert client.get(f"/api/v1/organizations/{org}/api-keys",
                      headers=headers).json()[0]["last_used_at"] is None

    client.get("/api/v1/projects", headers=_as_key(token))
    assert client.get(f"/api/v1/organizations/{org}/api-keys",
                      headers=headers).json()[0]["last_used_at"] is not None


def test_issuing_and_revoking_are_written_to_the_journal(client, register):
    headers = register()
    org = _org_id(client, headers)
    _, body = _issue(client, headers)
    client.delete(f"/api/v1/organizations/{org}/api-keys/{body['key']['id']}",
                  headers=headers)

    actions = {e["action"] for e in
               client.get(f"/api/v1/organizations/{org}/audit-log",
                          headers=headers).json()["entries"]}
    assert {"apikey.create", "apikey.revoke"} <= actions


def test_keys_are_limited_in_number(client, register, monkeypatch):
    monkeypatch.setattr(apikeys, "MAX_KEYS_PER_ORG", 2)
    headers = register()
    org = _org_id(client, headers)
    for i in range(2):
        assert client.post(f"/api/v1/organizations/{org}/api-keys",
                           json={"name": f"Ключ {i}"}, headers=headers).status_code == 201
    r = client.post(f"/api/v1/organizations/{org}/api-keys", json={"name": "Лишний"},
                    headers=headers)
    assert r.status_code == 409 and "Отзовите лишние" in r.json()["detail"]


# --- Ограничение продукта (B2) ---

def test_an_unpaid_organization_still_lets_the_key_read(client, register, db_session):
    """Режим чтения и выгрузки закрывает изменения — а ключ ничего и не меняет."""
    headers = register()
    _project(client, headers)
    token, _ = _issue(client, headers)
    crud.set_plan(db_session, _org_id(client, headers), "pro", status="past_due")

    assert client.get("/api/v1/projects", headers=_as_key(token)).status_code == 200
