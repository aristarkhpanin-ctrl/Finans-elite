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
