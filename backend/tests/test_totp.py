"""Второй фактор: одноразовые коды из приложения (ADMIN-DECOMPOSITION.md, C2).

Пароль был единственной дверью: подобрали или подсмотрели — и учётная запись чужая.
Второй фактор закрывает именно это.

Половина тестов здесь — про **возврат доступа**, а не про вход. Почты у платформы нет,
значит письма «восстановите доступ» не существует: потерянный телефон без резервных кодов
означал бы навсегда потерянную учётную запись. Поэтому коды обязательны, а последней
инстанцией остаётся платформа — и её сброс не бывает молчаливым.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from app import crud, totp


def _login(client, email="owner@e.ru", password="secret123", **body):
    return client.post("/api/v1/auth/login",
                       json={"email": email, "password": password, **body})


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _enable(client, headers) -> list[str]:
    """Включить второй фактор и вернуть резервные коды."""
    setup = client.post("/api/v1/auth/totp/setup", headers=headers).json()
    code = totp.code_at(setup["secret"])
    return client.post("/api/v1/auth/totp/enable", json={"code": code},
                       headers=headers).json()["codes"]


def _secret_of(client, headers) -> str:
    return client.post("/api/v1/auth/totp/setup", headers=headers).json()["secret"]


# --- Сама реализация TOTP ---

def test_code_matches_rfc_6238_reference_vector():
    """Проверка нашей реализации по эталону RFC 6238: секрет «12345678901234567890»
    в base32 — и три момента времени из приложения B стандарта.

    Без эталона «наш код сходится с нашим кодом» доказывает только внутреннюю
    согласованность — а приложение пользователя считает по стандарту, а не по нам.
    Ровно на этом тест и поймал первую версию: секрет был записан вдвое короче.
    """
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"      # base32 от «12345678901234567890»
    assert totp.code_at(secret, 59) == "287082"           # 94287082
    assert totp.code_at(secret, 1111111109) == "081804"   # 07081804
    assert totp.code_at(secret, 1234567890) == "005924"   # 89005924


def test_drift_of_one_window_is_accepted_and_two_is_not():
    """±30 секунд — это разошедшиеся часы телефона. Больше означало бы продлевать жизнь
    подсмотренному коду."""
    secret = totp.new_secret()
    now = time.time()
    assert totp.verify(secret, totp.code_at(secret, now - 30), now)
    assert totp.verify(secret, totp.code_at(secret, now + 30), now)
    assert not totp.verify(secret, totp.code_at(secret, now - 90), now)


def test_garbage_is_not_a_code():
    secret = totp.new_secret()
    for bad in ("", "123", "abcdef", "12345678", None):
        assert not totp.verify(secret, bad)  # type: ignore[arg-type]


def test_recovery_code_is_one_time():
    """Одноразовость — весь смысл резервного кода: подсмотренный на бумажке иначе
    работает вечно."""
    codes = totp.new_recovery_codes()
    stored = [totp.hash_code(c) for c in codes]
    left = totp.take_recovery_code(stored, codes[0])
    assert left is not None and len(left) == len(stored) - 1
    assert totp.take_recovery_code(left, codes[0]) is None


def test_recovery_code_is_read_from_paper():
    """Код переписывают с бумажки: отказать из-за строчной буквы или лишнего пробела
    значило бы потерять доступ на ровном месте."""
    codes = totp.new_recovery_codes()
    stored = [totp.hash_code(c) for c in codes]
    assert totp.take_recovery_code(stored, codes[0].lower().replace("-", " ")) is not None


def test_secret_is_shown_in_groups_and_as_a_link():
    """Ключ вводят руками — QR платформа не рисует, и сплошная строка из 32 знаков
    набирается с ошибкой примерно всегда."""
    secret = totp.new_secret()
    assert " " in totp.format_secret(secret)
    uri = totp.otpauth_uri(secret, "ivan@e.ru")
    assert uri.startswith("otpauth://totp/") and secret in uri and "issuer=" in uri


# --- Настройка ---

def test_setup_does_not_turn_the_factor_on(client, register):
    """Пока код не подтверждён, вход работает как прежде: иначе опечатки в приложении
    хватило бы, чтобы человек остался снаружи своей учётной записи."""
    headers = register()
    client.post("/api/v1/auth/totp/setup", headers=headers)

    status = client.get("/api/v1/auth/totp", headers=headers).json()
    assert status["enabled"] is False and status["pending"] is True
    assert _login(client).status_code == 200          # код не спрашивают


def test_enable_requires_a_matching_code(client, register):
    headers = register()
    client.post("/api/v1/auth/totp/setup", headers=headers)
    r = client.post("/api/v1/auth/totp/enable", json={"code": "000000"}, headers=headers)
    assert r.status_code == 400 and "время" in r.json()["detail"]


def test_enable_returns_recovery_codes_once(client, register):
    headers = register()
    codes = _enable(client, headers)
    assert len(codes) == totp.RECOVERY_COUNT
    # Второй раз их не отдают: хранятся отпечатки, как у пароля.
    status = client.get("/api/v1/auth/totp", headers=headers).json()
    assert status["enabled"] is True
    assert status["recovery_left"] == totp.RECOVERY_COUNT
    assert "codes" not in status


def test_second_setup_is_refused_while_enabled(client, register):
    headers = register()
    _enable(client, headers)
    assert client.post("/api/v1/auth/totp/setup", headers=headers).status_code == 409


# --- Вход ---

def test_login_without_the_code_asks_for_it(client, register):
    """Отдельный статус, а не 401: пароль **верен**, и человеку нужно не «войти заново»,
    а сделать второй шаг."""
    headers = register()
    _enable(client, headers)
    r = _login(client)
    assert r.status_code == 428 and "код" in r.json()["detail"].lower()


def test_login_with_the_code_works(client, register):
    headers = register()
    secret = _secret_of(client, headers)
    client.post("/api/v1/auth/totp/enable", json={"code": totp.code_at(secret)},
                headers=headers)
    r = _login(client, totp_code=totp.code_at(secret))
    assert r.status_code == 200 and r.json()["access_token"]


def test_wrong_code_is_refused_and_written_to_the_journal(client, register):
    headers = register()
    org = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    _enable(client, headers)

    assert _login(client, totp_code="000000").status_code == 401
    actions = {e["action"] for e in
               client.get(f"/api/v1/organizations/{org}/audit-log",
                          headers=headers).json()["entries"]}
    assert "auth.totp_failed" in actions


def test_guessing_is_closed_by_account_not_by_address(client, register, db_session):
    """Ограничение по адресу от подбора шестизначного кода не спасает: адреса меняются,
    а учётная запись одна."""
    headers = register()
    _enable(client, headers)
    for _ in range(crud.TOTP_MAX_FAILURES):
        assert _login(client, totp_code="000000").status_code == 401

    blocked = _login(client, totp_code="000000")
    assert blocked.status_code == 429 and "мин" in blocked.json()["detail"]


def test_a_correct_code_clears_the_counter(client, register, db_session):
    headers = register()
    secret = _secret_of(client, headers)
    client.post("/api/v1/auth/totp/enable", json={"code": totp.code_at(secret)},
                headers=headers)
    _login(client, totp_code="000000")
    _login(client, totp_code=totp.code_at(secret))

    user = crud.get_user_by_email(db_session, "owner@e.ru")
    db_session.refresh(user)
    assert user.totp_failures == 0


def test_lock_lets_go_when_it_expires(client, register, db_session):
    headers = register()
    secret = _secret_of(client, headers)
    client.post("/api/v1/auth/totp/enable", json={"code": totp.code_at(secret)},
                headers=headers)
    user = crud.get_user_by_email(db_session, "owner@e.ru")
    user.totp_locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    assert _login(client, totp_code=totp.code_at(secret)).status_code == 200


# --- Возврат доступа ---

def test_recovery_code_gets_in_and_says_how_many_are_left(client, register):
    """Молча съеденный код кончится в самый неподходящий момент."""
    headers = register()
    codes = _enable(client, headers)

    r = _login(client, totp_code=codes[0])
    assert r.status_code == 200
    assert "резервному коду" in r.json()["notice"]
    assert str(totp.RECOVERY_COUNT - 1) in r.json()["notice"]

    # И этот код больше не работает.
    assert _login(client, totp_code=codes[0]).status_code == 401


def test_recovery_codes_can_be_reissued_with_the_password(client, register):
    headers = register()
    codes = _enable(client, headers)
    fresh = client.post("/api/v1/auth/totp/recovery-codes",
                        json={"password": "secret123"}, headers=headers).json()["codes"]
    assert set(fresh) != set(codes)
    assert _login(client, totp_code=codes[0]).status_code == 401     # прежние мертвы
    assert _login(client, totp_code=fresh[0]).status_code == 200


def test_disabling_requires_the_password(client, register):
    """Выключить второй фактор — ровно то, что сделает угонщик, дорвавшийся до открытой
    вкладки. Пароль здесь — разница между «украли сессию» и «украли учётную запись»."""
    headers = register()
    _enable(client, headers)
    assert client.post("/api/v1/auth/totp/disable", json={"password": "не тот"},
                       headers=headers).status_code == 400
    assert client.post("/api/v1/auth/totp/disable", json={"password": "secret123"},
                       headers=headers).status_code == 204
    assert _login(client).status_code == 200


def test_operator_reset_is_the_last_resort_and_is_never_silent(client, register,
                                                                db_session):
    """Платформа — последняя инстанция, потому что письма «восстановите доступ» не
    существует. Именно поэтому сброс виден: он делает ровно то, ради чего второй фактор
    и ставили."""
    staff = register(email="staff@e.ru", org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, "staff@e.ru"),
                   is_staff=True)
    owner = register(email="o@e.ru", org="Клиент")
    org = client.get("/api/v1/organizations", headers=owner).json()[0]["id"]
    user_id = client.get("/api/v1/auth/me", headers=owner).json()["id"]
    _enable(client, owner)
    assert _login(client, email="o@e.ru").status_code == 428

    r = client.delete(f"/api/v1/admin/users/{user_id}/totp", headers=staff)
    assert r.status_code == 200
    assert _login(client, email="o@e.ru").status_code == 200

    theirs = {e["action"] for e in
              client.get(f"/api/v1/organizations/{org}/audit-log",
                         headers=owner).json()["entries"]}
    ours = {e["action"] for e in
            client.get("/api/v1/admin/log", headers=staff).json()["entries"]}
    assert "staff.totp_reset" in theirs and "staff.totp_reset" in ours


def test_reset_of_an_unset_factor_says_so(client, register, db_session):
    staff = register(email="staff@e.ru", org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, "staff@e.ru"),
                   is_staff=True)
    owner = register(email="o@e.ru", org="Клиент")
    user_id = client.get("/api/v1/auth/me", headers=owner).json()["id"]
    assert client.delete(f"/api/v1/admin/users/{user_id}/totp",
                         headers=staff).status_code == 409


# --- Что платформа не делает ---

def test_owner_is_advised_not_forced(client, register):
    """Принудительное включение без второго канала восстановления заперло бы того, кто
    потеряет и телефон, и коды: решение «сделать обязательным» — за владельцем платформы,
    а не за кодом. Отказ назван в декомпозиции, а рекомендация — на экране."""
    owner = register()
    status = client.get("/api/v1/auth/totp", headers=owner).json()
    assert status["recommended"] is True and status["enabled"] is False
    assert _login(client).status_code == 200      # без второго фактора вход работает


def test_ordinary_member_is_not_nagged(client, register):
    owner = register()
    org = client.get("/api/v1/organizations", headers=owner).json()[0]["id"]
    member = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "k@e.ru", "full_name": "К", "role": "editor"},
                         headers=owner).json()
    token = client.post("/api/v1/auth/activate",
                        json={"token": member["invite_token"],
                              "password": "kollega-parol7"}).json()["access_token"]
    status = client.get("/api/v1/auth/totp", headers=_headers(token)).json()
    assert status["recommended"] is False
