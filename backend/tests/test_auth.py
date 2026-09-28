"""Тесты аутентификации (6.3): регистрация, вход, текущий пользователь."""


def _register(client, email="user@e.ru"):
    return client.post("/api/v1/auth/register", json={
        "email": email, "password": "secret123", "full_name": "Иван",
        "organization_name": "Орг",
    })


def test_register_returns_token(client):
    r = _register(client)
    assert r.status_code == 201
    assert r.json()["access_token"]
    assert r.json()["token_type"] == "bearer"


def test_register_duplicate_email_409(client):
    _register(client)
    assert _register(client).status_code == 409


def test_login_ok(client):
    _register(client)
    r = client.post("/api/v1/auth/login", json={"email": "user@e.ru", "password": "secret123"})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_wrong_password_401(client):
    _register(client)
    r = client.post("/api/v1/auth/login", json={"email": "user@e.ru", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user_401(client):
    r = client.post("/api/v1/auth/login", json={"email": "nobody@e.ru", "password": "x"})
    assert r.status_code == 401


def test_me_returns_current_user(client):
    token = _register(client).json()["access_token"]
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "user@e.ru"


def test_me_invalid_token_401(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_invited_user_cannot_login(client, auth_headers):
    # участник, добавленный по email (без пароля), не может войти, пока не активирован
    org = client.post("/api/v1/organizations", json={"name": "О"}, headers=auth_headers).json()["id"]
    client.post(f"/api/v1/organizations/{org}/members",
                json={"email": "invited@e.ru"}, headers=auth_headers)
    r = client.post("/api/v1/auth/login", json={"email": "invited@e.ru", "password": "x"})
    assert r.status_code == 401


# --- Активация приглашения и профиль (Экран 15; пробел №12 сверки) ---

def _org(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _invite(client, owner, email="new@e.ru", role="analyst") -> str:
    oid = _org(client, owner)
    r = client.post(f"/api/v1/organizations/{oid}/members",
                    json={"email": email, "full_name": "Приглашённый", "role": role},
                    headers=owner)
    assert r.status_code == 201
    return r.json()["invite_token"]


def test_invited_user_can_activate_and_work(client, register):
    """Приглашение теперь ведёт куда-то.

    До этого приглашённый участник существовал, но войти не мог никогда: он заводится
    без пароля, а способа его задать не было.
    """
    owner = register(email="own@e.ru", org="Орг П")
    token = _invite(client, owner)
    assert token

    r = client.post("/api/v1/auth/activate",
                    json={"token": token, "password": "newpass123", "full_name": "Аналитик"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["email"] == "new@e.ru" and me["full_name"] == "Аналитик"
    # и он действительно в организации пригласившего
    assert _org(client, headers) == _org(client, owner)

    # обычный вход теперь тоже работает
    assert client.post("/api/v1/auth/login",
                       json={"email": "new@e.ru", "password": "newpass123"}).status_code == 200


def test_invite_token_is_not_a_login_token(client, register):
    """Токеном приглашения нельзя войти — им можно только завести пароль.

    Иначе приглашённый попадал бы внутрь **до** того, как задал пароль, а сама
    ссылка-приглашение становилась бы вечным пропуском в чужую организацию.
    """
    owner = register(email="own2@e.ru", org="Орг П2")
    token = _invite(client, owner, email="n2@e.ru")
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_access_token_cannot_activate(client, register):
    """И наоборот: токен входа не годится для активации — назначение проверяется в обе стороны."""
    owner = register(email="own3@e.ru", org="Орг П3")
    access = owner["Authorization"].split(" ", 1)[1]
    r = client.post("/api/v1/auth/activate",
                    json={"token": access, "password": "whatever123"})
    assert r.status_code == 400


def test_activation_is_single_use(client, register):
    """Повторная активация отклоняется.

    Иначе ссылка-приглашение осталась бы вечным способом сбросить чужой пароль,
    минуя знание текущего.
    """
    owner = register(email="own4@e.ru", org="Орг П4")
    token = _invite(client, owner, email="n4@e.ru")
    assert client.post("/api/v1/auth/activate",
                       json={"token": token, "password": "pervyi-parol7"}).status_code == 200
    r = client.post("/api/v1/auth/activate",
                    json={"token": token, "password": "vtoroy-parol7"})
    assert r.status_code == 409
    # старый пароль в силе, новый не сработал
    assert client.post("/api/v1/auth/login",
                       json={"email": "n4@e.ru", "password": "pervyi-parol7"}).status_code == 200
    assert client.post("/api/v1/auth/login",
                       json={"email": "n4@e.ru", "password": "vtoroy-parol7"}).status_code == 401


def test_invite_token_absent_for_existing_user(client, register):
    """Уже зарегистрированному участнику ссылка активации не выдаётся — у него есть пароль."""
    owner = register(email="own5@e.ru", org="Орг П5")
    register(email="exists@e.ru", org="Своя")
    oid = _org(client, owner)
    r = client.post(f"/api/v1/organizations/{oid}/members",
                    json={"email": "exists@e.ru", "full_name": "", "role": "viewer"},
                    headers=owner)
    assert r.status_code == 201 and r.json()["invite_token"] is None


def test_invite_token_not_leaked_in_member_list(client, register):
    """В списке участников токена нет: там он был бы пропуском в чужой аккаунт."""
    owner = register(email="own6@e.ru", org="Орг П6")
    _invite(client, owner, email="n6@e.ru")
    members = client.get(f"/api/v1/organizations/{_org(client, owner)}/members",
                         headers=owner).json()
    assert all(m.get("invite_token") is None for m in members)


def test_profile_name_can_be_changed(client, auth_headers):
    r = client.patch("/api/v1/auth/me", json={"full_name": "Новое имя"}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["full_name"] == "Новое имя"
    assert client.get("/api/v1/auth/me", headers=auth_headers).json()["full_name"] == "Новое имя"


def test_password_change_requires_current(client, register):
    """Смена пароля требует текущий: иначе украденная сессия запирает владельца снаружи."""
    headers = register(email="pw@e.ru", org="Орг Пароль")
    bad = client.post("/api/v1/auth/password",
                      json={"current_password": "wrong123", "new_password": "brandnew123"},
                      headers=headers)
    assert bad.status_code == 400
    assert client.post("/api/v1/auth/login",
                       json={"email": "pw@e.ru", "password": "secret123"}).status_code == 200

    ok = client.post("/api/v1/auth/password",
                     json={"current_password": "secret123", "new_password": "brandnew123"},
                     headers=headers)
    assert ok.status_code == 204
    assert client.post("/api/v1/auth/login",
                       json={"email": "pw@e.ru", "password": "brandnew123"}).status_code == 200
    assert client.post("/api/v1/auth/login",
                       json={"email": "pw@e.ru", "password": "secret123"}).status_code == 401


def test_short_password_rejected_everywhere(client, register):
    """Одно правило длины на все три двери: регистрация, активация, смена."""
    assert client.post("/api/v1/auth/register", json={
        "email": "short@e.ru", "password": "1234", "full_name": "",
        "organization_name": "Орг"}).status_code == 422

    owner = register(email="own7@e.ru", org="Орг П7")
    token = _invite(client, owner, email="n7@e.ru")
    assert client.post("/api/v1/auth/activate",
                       json={"token": token, "password": "1234"}).status_code == 422
    assert client.post("/api/v1/auth/password",
                       json={"current_password": "secret123", "new_password": "1234"},
                       headers=owner).status_code == 422


# --- Сброс пароля: ссылку выдаёт администратор организации ---

def _member(client, owner, email: str, role: str = "analyst") -> str:
    """Завести участника с паролем; вернуть его user_id."""
    token = _invite(client, owner, email=email, role=role)
    r = client.post("/api/v1/auth/activate", json={"token": token, "password": "pervyi-parol7"})
    assert r.status_code == 200
    me = client.get("/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    return me.json()["id"]


def _link(client, owner, user_id: str):
    return client.post(
        f"/api/v1/organizations/{_org(client, owner)}/members/{user_id}/access-link",
        headers=owner)


def test_anonymous_recovery_hands_out_nothing(client, register):
    """Восстановление без входа появилось (D1) — но оно ничего не отдаёт просившему.

    Запрет был условным: «сброс по одному лишь названному адресу — способ угнать
    аккаунт, **пока нет почты**». Почта появилась, и условие снято тем, что его
    поставило: ссылка уходит **в ящик**, то есть тому, кто им владеет, а просивший
    получает один и тот же ответ на любой адрес. Здесь проверяется именно это: в ответе
    нет ни токена, ни ссылки, ни признака, что адрес существует.

    Ручная дорога рядом никуда не делась и по-прежнему требует прав: ссылку участнику
    выдаёт администратор, и без токена этого не сделать.
    """
    register(email="anon-own@e.ru", org="Орг А")
    r = client.post("/api/v1/auth/forgot-password", json={"email": "anon-own@e.ru"})
    body = r.text
    assert "token" not in body and "activate" not in body

    owner = register(email="anon2@e.ru", org="Орг Б")
    uid = _member(client, owner, "anon-m@e.ru")
    # без токена ссылку не выдают
    r = client.post(
        f"/api/v1/organizations/{_org(client, owner)}/members/{uid}/access-link")
    assert r.status_code in (401, 403)


def test_admin_issues_reset_link_and_member_regains_access(client, register):
    """Забытый пароль перестал означать потерю учётной записи навсегда."""
    owner = register(email="res-own@e.ru", org="Орг Р")
    uid = _member(client, owner, "res-m@e.ru")

    r = _link(client, owner, uid)
    assert r.status_code == 200 and r.json()["kind"] == "reset"

    a = client.post("/api/v1/auth/activate",
                    json={"token": r.json()["token"], "password": "vtoroy-parol7"})
    assert a.status_code == 200
    assert client.post("/api/v1/auth/login",
                       json={"email": "res-m@e.ru", "password": "vtoroy-parol7"}).status_code == 200
    # прежний пароль больше не работает
    assert client.post("/api/v1/auth/login",
                       json={"email": "res-m@e.ru", "password": "pervyi-parol7"}).status_code == 401


def test_reset_link_is_single_use(client, register):
    """Одноразовость держится на отпечатке пароля — таблицы под это не заводили."""
    owner = register(email="once-own@e.ru", org="Орг О")
    uid = _member(client, owner, "once-m@e.ru")
    token = _link(client, owner, uid).json()["token"]
    assert client.post("/api/v1/auth/activate",
                       json={"token": token, "password": "vtoroy-parol7"}).status_code == 200
    r = client.post("/api/v1/auth/activate",
                    json={"token": token, "password": "tretiy-parol7"})
    assert r.status_code == 409
    assert client.post("/api/v1/auth/login",
                       json={"email": "once-m@e.ru", "password": "vtoroy-parol7"}).status_code == 200


def test_reset_link_dies_when_the_user_changes_password_himself(client, register):
    """Вспомнил пароль и сменил сам — выданная ссылка обязана умереть."""
    owner = register(email="self-own@e.ru", org="Орг С")
    uid = _member(client, owner, "self-m@e.ru")
    token = _link(client, owner, uid).json()["token"]

    login = client.post("/api/v1/auth/login",
                        json={"email": "self-m@e.ru", "password": "pervyi-parol7"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.post("/api/v1/auth/password",
                       json={"current_password": "pervyi-parol7", "new_password": "vladelec-parol7"},
                       headers=headers).status_code == 204

    r = client.post("/api/v1/auth/activate",
                    json={"token": token, "password": "perehvat-parol7"})
    assert r.status_code == 409


def test_owner_gets_no_access_link(client, register):
    """Иначе администратор сбрасывает пароль владельцу и забирает организацию."""
    owner = register(email="ow-own@e.ru", org="Орг В")
    me = client.get("/api/v1/auth/me", headers=owner).json()["id"]
    r = _link(client, owner, me)
    assert r.status_code == 409
    assert "владельц" in r.json()["detail"].lower()


def test_member_of_several_organizations_gets_no_link(client, register):
    """Пароль один на платформу: сброс отсюда открыл бы доступ к чужим организациям."""
    owner = register(email="multi-own@e.ru", org="Орг М1")
    other = register(email="multi-m@e.ru", org="Своя")
    uid = client.get("/api/v1/auth/me", headers=other).json()["id"]
    oid = _org(client, owner)
    assert client.post(f"/api/v1/organizations/{oid}/members",
                       json={"email": "multi-m@e.ru", "full_name": "", "role": "viewer"},
                       headers=owner).status_code == 201

    r = _link(client, owner, uid)
    assert r.status_code == 409
    assert "других организациях" in r.json()["detail"]


def test_access_link_reissues_an_invitation_when_there_is_no_password(client, register):
    """Потерянное приглашение — тот же тупик, и лечится той же кнопкой."""
    owner = register(email="lost-own@e.ru", org="Орг Л")
    _invite(client, owner, email="lost-m@e.ru")
    members = client.get(f"/api/v1/organizations/{_org(client, owner)}/members",
                         headers=owner).json()
    uid = [m for m in members if m["email"] == "lost-m@e.ru"][0]["user_id"]

    r = _link(client, owner, uid)
    assert r.status_code == 200 and r.json()["kind"] == "invite"
    assert client.post("/api/v1/auth/activate",
                       json={"token": r.json()["token"], "password": "svezhiy-parol7"}
                       ).status_code == 200


def test_access_link_requires_member_manage(client, register):
    """Выдавать ссылки входа может владелец или администратор, а не всякий участник."""
    owner = register(email="perm-own@e.ru", org="Орг П")
    uid = _member(client, owner, "perm-m@e.ru", role="viewer")
    token = _invite(client, owner, email="perm-v@e.ru", role="viewer")
    viewer = client.post("/api/v1/auth/activate",
                         json={"token": token, "password": "nabludatel7"}).json()
    headers = {"Authorization": f"Bearer {viewer['access_token']}"}
    r = client.post(
        f"/api/v1/organizations/{_org(client, owner)}/members/{uid}/access-link",
        headers=headers)
    assert r.status_code == 403


def test_access_link_reaches_the_audit_log(client, register):
    """Ссылкой получают доступ к учётной записи — в журнале это событие обязано быть."""
    owner = register(email="log-own@e.ru", org="Орг Ж")
    uid = _member(client, owner, "log-m@e.ru")
    _link(client, owner, uid)
    entries = client.get(f"/api/v1/organizations/{_org(client, owner)}/audit-log",
                         headers=owner).json()["entries"]
    assert any(e["action"] == "member.access_link" for e in entries)
