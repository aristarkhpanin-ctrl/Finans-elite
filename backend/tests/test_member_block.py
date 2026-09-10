"""Приостановка доступа участника (ADMIN-DECOMPOSITION.md, фаза A1).

Отстранить сотрудника было нечем: единственное доступное действие — удалить его из
организации, а это другое. Удаление стирает связь и историю роли; уволенного на время
проверки возвращают одним движением, а удалённого заводят заново.

Проверяется то, на чём держится смысл функции: отзыв **мгновенный** (иначе отстранённый
работает ещё сутки — столько живёт выданный токен), причина **названа** участнику,
блокируется **членство**, а не учётная запись (в других организациях человек работает),
и приостановленный **остаётся в списке** — исчезнувший читался бы как удалённый.
"""
from __future__ import annotations


def _members_url(client, headers) -> str:
    org = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return f"/api/v1/organizations/{org}/members"


def _add(client, headers, email="сотрудник@e.ru", role="editor") -> dict:
    return client.post(_members_url(client, headers),
                       json={"email": email, "full_name": "Сотрудник", "role": role},
                       headers=headers).json()


def _login(client, email: str, password: str = "secret123") -> dict:
    token = client.post("/api/v1/auth/login",
                        json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _activate(client, member: dict, password: str = "secret123") -> dict:
    """Приглашённый заводит пароль и получает рабочий доступ."""
    client.post("/api/v1/auth/activate",
                json={"token": member["invite_token"], "password": password})
    return _login(client, member["email"])


# --- отзыв доступа ---

def test_block_takes_effect_immediately_on_an_already_issued_token(client, auth_headers):
    """Токен живёт сутки; если блокировка ждёт его истечения — она бесполезна."""
    member = _add(client, auth_headers)
    worker = _activate(client, member)
    assert client.get("/api/v1/projects", headers=worker).status_code == 200

    url = _members_url(client, auth_headers) + f"/{member['user_id']}/block"
    assert client.post(url, json={"reason": "увольнение"}, headers=auth_headers).status_code == 200

    # Тот же самый токен, выданный до блокировки.
    r = client.get("/api/v1/projects", headers=worker)
    assert r.status_code == 403
    assert "приостановлен" in r.json()["detail"]


def test_refusal_names_the_reason_and_is_not_a_login_screen(client, auth_headers):
    """403, а не 401: токен действителен, и отправлять человека на вход — врать ему."""
    member = _add(client, auth_headers)
    worker = _activate(client, member)
    client.post(_members_url(client, auth_headers) + f"/{member['user_id']}/block",
                json={"reason": "проверка службы безопасности"}, headers=auth_headers)

    r = client.get("/api/v1/projects", headers=worker)
    assert r.status_code == 403
    assert "проверка службы безопасности" in r.json()["detail"]


def test_every_door_into_the_organization_is_closed(client, auth_headers):
    """Проверка стоит в зависимостях, через которые проходит любой запрос к данным."""
    member = _add(client, auth_headers)
    worker = _activate(client, member)
    org = client.get("/api/v1/organizations", headers=worker).json()[0]["id"]
    client.post(_members_url(client, auth_headers) + f"/{member['user_id']}/block",
                json={"reason": "увольнение"}, headers=auth_headers)

    # права в текущей организации, членство по пути, право по пути
    assert client.get("/api/v1/projects", headers=worker).status_code == 403
    assert client.get(f"/api/v1/organizations/{org}/benchmarks",
                      headers=worker).status_code == 403
    assert client.get(f"/api/v1/organizations/{org}/members",
                      headers=worker).status_code == 403
    assert client.get("/api/v1/audit/subjects", headers=worker).status_code == 403


def test_unblock_returns_access(client, auth_headers):
    member = _add(client, auth_headers)
    worker = _activate(client, member)
    url = _members_url(client, auth_headers) + f"/{member['user_id']}/block"
    client.post(url, json={"reason": "разбор"}, headers=auth_headers)
    assert client.get("/api/v1/projects", headers=worker).status_code == 403

    r = client.delete(url, headers=auth_headers)
    assert r.status_code == 200 and r.json()["blocked"] is False
    # Причина стёрта: она рассказывала бы о действующем участнике то, чего уже нет.
    assert r.json()["block_reason"] == "" and r.json()["blocked_by"] == ""
    assert client.get("/api/v1/projects", headers=worker).status_code == 200


# --- границы права ---

def test_owner_cannot_be_blocked(client, auth_headers):
    """Иначе администратор отстраняет владельца и забирает организацию с тарифом."""
    owner_id = client.get("/api/v1/auth/me", headers=auth_headers).json()["id"]
    admin = _add(client, auth_headers, email="админ@e.ru", role="admin")
    admin_h = _activate(client, admin)

    r = client.post(_members_url(client, auth_headers) + f"/{owner_id}/block",
                    json={"reason": "захват"}, headers=admin_h)
    assert r.status_code == 409 and "владельца" in r.json()["detail"]


def test_nobody_can_block_themselves(client, auth_headers):
    """Администратор запер бы себя снаружи, и снять блокировку было бы некому."""
    admin = _add(client, auth_headers, email="админ@e.ru", role="admin")
    admin_h = _activate(client, admin)
    r = client.post(_members_url(client, auth_headers) + f"/{admin['user_id']}/block",
                    json={"reason": "случайно"}, headers=admin_h)
    assert r.status_code == 409 and "себя" in r.json()["detail"]


def test_ordinary_member_cannot_block_anyone(client, auth_headers):
    member = _add(client, auth_headers)
    worker = _activate(client, member)
    other = _add(client, auth_headers, email="другой@e.ru")
    r = client.post(_members_url(client, auth_headers) + f"/{other['user_id']}/block",
                    json={"reason": "просто так"}, headers=worker)
    assert r.status_code == 403


def test_reason_is_required(client, auth_headers):
    """Блокировка без причины неотличима от ошибки — и для участника, и для того,
    кто будет её снимать."""
    member = _add(client, auth_headers)
    url = _members_url(client, auth_headers) + f"/{member['user_id']}/block"
    assert client.post(url, json={"reason": ""}, headers=auth_headers).status_code == 422
    assert client.post(url, json={}, headers=auth_headers).status_code == 422


def test_double_block_and_empty_unblock_are_refused_with_a_reason(client, auth_headers):
    member = _add(client, auth_headers)
    url = _members_url(client, auth_headers) + f"/{member['user_id']}/block"
    assert client.delete(url, headers=auth_headers).status_code == 409     # ещё не блокирован
    client.post(url, json={"reason": "раз"}, headers=auth_headers)
    r = client.post(url, json={"reason": "два"}, headers=auth_headers)
    assert r.status_code == 409 and "уже" in r.json()["detail"]


# --- членство, а не учётная запись ---

def test_block_in_one_organization_leaves_the_other_alone(client, auth_headers, register):
    """Администратор одной организации не распоряжается доступом в чужой — тот же
    довод, по которому ему не выдают ссылку сброса пароля участнику нескольких."""
    other_owner = register(email="вторая@e.ru", org="Вторая")
    member = _add(client, auth_headers)                       # в первой организации
    worker = _activate(client, member)
    # тот же человек — участник второй организации
    client.post(_members_url(client, other_owner),
                json={"email": member["email"], "full_name": "Сотрудник", "role": "editor"},
                headers=other_owner)
    second = client.get("/api/v1/organizations", headers=other_owner).json()[0]["id"]

    client.post(_members_url(client, auth_headers) + f"/{member['user_id']}/block",
                json={"reason": "увольнение"}, headers=auth_headers)

    # Во второй организации он продолжает работать — и попадает туда по умолчанию,
    # а не упирается в приостановленное членство первой.
    assert client.get("/api/v1/projects", headers=worker).status_code == 200
    assert client.get("/api/v1/projects",
                      headers={**worker, "X-Organization-Id": second}).status_code == 200


def test_explicit_request_to_the_blocked_organization_still_refuses(client, auth_headers,
                                                                    register):
    member = _add(client, auth_headers)
    worker = _activate(client, member)
    first = client.get("/api/v1/organizations", headers=auth_headers).json()[0]["id"]
    other_owner = register(email="вторая@e.ru", org="Вторая")
    client.post(_members_url(client, other_owner),
                json={"email": member["email"], "full_name": "Сотрудник", "role": "editor"},
                headers=other_owner)
    client.post(_members_url(client, auth_headers) + f"/{member['user_id']}/block",
                json={"reason": "увольнение"}, headers=auth_headers)

    r = client.get("/api/v1/projects", headers={**worker, "X-Organization-Id": first})
    assert r.status_code == 403 and "приостановлен" in r.json()["detail"]


# --- видимость и след ---

def test_blocked_member_stays_in_the_list_with_the_reason(client, auth_headers):
    """Исчезнувший из списка читался бы как удалённый, а это другое состояние."""
    member = _add(client, auth_headers)
    client.post(_members_url(client, auth_headers) + f"/{member['user_id']}/block",
                json={"reason": "увольнение"}, headers=auth_headers)

    row = next(m for m in client.get(_members_url(client, auth_headers),
                                     headers=auth_headers).json()
               if m["user_id"] == member["user_id"])
    assert row["blocked"] is True
    assert row["block_reason"] == "увольнение" and row["blocked_at"]
    assert row["blocked_by"] == "owner@e.ru"      # кто отстранил — видно
    assert row["role"] == "editor"                # роль сохранена: вернуть можно как было


def test_block_and_unblock_are_written_to_the_journal(client, auth_headers):
    member = _add(client, auth_headers)
    org = client.get("/api/v1/organizations", headers=auth_headers).json()[0]["id"]
    url = _members_url(client, auth_headers) + f"/{member['user_id']}/block"
    client.post(url, json={"reason": "увольнение"}, headers=auth_headers)
    client.delete(url, headers=auth_headers)

    log = client.get(f"/api/v1/organizations/{org}/audit-log", headers=auth_headers).json()
    actions = [e["action"] for e in log["entries"]]
    assert "member.block" in actions and "member.unblock" in actions
    blocked = next(e for e in log["entries"] if e["action"] == "member.block")
    assert blocked["details"] == "увольнение"     # причина остаётся в журнале навсегда
