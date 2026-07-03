"""Тесты ограничения частоты запросов к /auth (защита от перебора)."""
from app.ratelimit import _store

# Уникальный IP на тест — ключ окна изолирован от остального прогона.
_XFF = {"X-Forwarded-For": "203.0.113.7"}
_XFF2 = {"X-Forwarded-For": "203.0.113.8"}


def _login(client, headers):
    return client.post("/api/v1/auth/login",
                       json={"email": "nobody@e.ru", "password": "x"}, headers=headers)


def test_login_rate_limited_after_threshold(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    _store.clear()
    # Лимит логина — 20/мин: первые 20 попыток проходят (401 на неверных данных).
    for _ in range(20):
        assert _login(client, _XFF).status_code == 401
    # 21-я — отбита ограничителем.
    blocked = _login(client, _XFF)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


def test_rate_limit_is_per_ip(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    _store.clear()
    for _ in range(20):
        _login(client, _XFF)
    assert _login(client, _XFF).status_code == 429      # исчерпан
    assert _login(client, _XFF2).status_code == 401      # другой IP — свободен


def test_spoofed_xff_first_hop_does_not_bypass(client, monkeypatch):
    # Атакующий меняет ПЕРВЫЙ X-Forwarded-For на каждый запрос, но X-Real-IP (его
    # выставляет nginx на реальный IP) один → лимит срабатывает, обхода нет.
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    _store.clear()
    real = {"X-Real-IP": "198.51.100.5"}
    for i in range(20):
        client.post("/api/v1/auth/login", json={"email": "n@e.ru", "password": "x"},
                    headers={**real, "X-Forwarded-For": f"1.2.3.{i}"})
    blocked = client.post("/api/v1/auth/login", json={"email": "n@e.ru", "password": "x"},
                          headers={**real, "X-Forwarded-For": "203.0.113.250"})
    assert blocked.status_code == 429


def test_rate_limit_disabled_by_default(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    _store.clear()
    # При выключенном лимите превышение порога не приводит к 429.
    codes = {_login(client, _XFF).status_code for _ in range(25)}
    assert codes == {401}
