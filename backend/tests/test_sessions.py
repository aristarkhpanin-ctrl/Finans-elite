"""Сеансы входа и отзыв доступа (ADMIN-DECOMPOSITION.md, C1).

Токен жил сутки и не отзывался ничем: украденный — работал до конца срока, а человек не
мог ни увидеть чужой вход, ни закрыть его. Фаза заводит **реестр входов**: каждый токен
привязан к строке, которую владелец видит и закрывает сам.

Это не список отозванных токенов, который план запрещал заводить без нужды. Отрицательный
список ничего не даёт человеку и живёт ради инфраструктуры; реестр даёт обратное — видимую
и управляемую картину, а отзыв получается побочным эффектом.

Второго механизма (``token_version`` из плана) здесь нет намеренно: сеансы покрывают его
целиком, а два источника ответа на вопрос «действителен ли токен» однажды разошлись бы.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app import crud
from app.security import JWT_ALG, JWT_SECRET, JWT_TTL_SECONDS, REMEMBER_TTL_SECONDS
from app.sessions import client_ip, device_label


def _login(client, email="owner@e.ru", password="secret123", **body) -> str:
    return client.post("/api/v1/auth/login",
                       json={"email": email, "password": password, **body}).json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _sessions(client, headers) -> list[dict]:
    return client.get("/api/v1/auth/sessions", headers=headers).json()


# --- Подпись устройства и адрес ---

def test_device_label_says_unknown_instead_of_going_blank():
    """Пустая ячейка читается как «данных нет»; «устройство неизвестно» честнее —
    данные есть, но они ничего не говорят."""
    assert device_label("") == "Устройство неизвестно"
    assert device_label(None) == "Устройство неизвестно"


def test_device_label_prefers_the_specific_browser():
    """У Edge в строке есть «Chrome», у Chrome — «Safari»: частное обязано идти раньше
    общего, иначе все окажутся в Safari."""
    edge = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like "
            "Gecko) Chrome/120 Safari/537.36 Edg/120")
    chrome = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
              "like Gecko) Chrome/120 Safari/537.36")
    assert device_label(edge) == "Edge · Windows"
    assert device_label(chrome) == "Chrome · macOS"
    assert device_label("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604") == "Safari · iPhone"


def test_client_ip_takes_the_first_in_the_chain():
    """Цепочку дописывают прокси слева направо: левее всех тот, кто обратился первым."""
    assert client_ip(forwarded_for="203.0.113.7, 10.0.0.1", remote="10.0.0.1") == "203.0.113.7"
    assert client_ip(forwarded_for=None, remote="198.51.100.4") == "198.51.100.4"
    assert client_ip(forwarded_for="", remote="") == ""


# --- Реестр входов ---

def test_login_creates_a_visible_session(client, register):
    headers = register()
    rows = _sessions(client, headers)
    assert len(rows) == 1
    assert rows[0]["current"] is True         # без пометки человек закрыл бы себя
    assert rows[0]["device"]
    assert rows[0]["expires_at"]


def test_each_login_is_its_own_session(client, register):
    register()                                   # регистрация — это тоже вход
    a, b = _headers(_login(client)), _headers(_login(client))
    assert len({s["id"] for s in _sessions(client, a)}) == 3
    # Каждый видит текущим **свой** вход, а не первый попавшийся.
    assert next(s for s in _sessions(client, a) if s["current"])["id"] != \
           next(s for s in _sessions(client, b) if s["current"])["id"]


def test_revoking_a_session_closes_it_immediately(client, register):
    """Отзыв мгновенный: состояние читается из базы на каждом запросе, а не из токена."""
    register()
    stale = _headers(_login(client))
    fresh = _headers(_login(client))
    stale_id = next(s["id"] for s in _sessions(client, stale) if s["current"])

    assert client.delete(f"/api/v1/auth/sessions/{stale_id}",
                         headers=fresh).status_code == 204
    refused = client.get("/api/v1/projects", headers=stale)
    assert refused.status_code == 401
    assert "войдите снова" in refused.json()["detail"]
    assert stale_id not in {s["id"] for s in _sessions(client, fresh)}


def test_closed_sessions_disappear_from_the_list(client, register):
    """Список мёртвых входов не отвечает на вопрос, ради которого его открывают."""
    register()
    first = _headers(_login(client))
    second = _headers(_login(client))
    first_id = next(s["id"] for s in _sessions(client, first) if s["current"])
    client.delete(f"/api/v1/auth/sessions/{first_id}", headers=second)
    assert first_id not in {s["id"] for s in _sessions(client, second)}


def test_someone_elses_session_is_not_found_rather_than_forbidden(client, register):
    """Чужой вход не находится, а не отказывается по правам: знать о существовании
    чужих входов незачем."""
    a = register(email="a@e.ru", org="Первая")
    register(email="b@e.ru", org="Вторая")
    b_token = client.post("/api/v1/auth/login",
                          json={"email": "b@e.ru", "password": "secret123"}
                          ).json()["access_token"]
    b_session = next(s["id"] for s in _sessions(client, _headers(b_token)) if s["current"])

    assert client.delete(f"/api/v1/auth/sessions/{b_session}", headers=a).status_code == 404
    # И чужой вход при этом остался жив — отказ не сработал «наполовину».
    assert client.get("/api/v1/auth/sessions", headers=_headers(b_token)).status_code == 200


def test_revoke_all_closes_the_current_one_too(client, register):
    """Кнопку жмут, когда не уверены, что контролируют учётную запись: оставленный
    «свой» вход в такой ситуации — ровно тот, из-за которого всё и началось."""
    register()
    first = _headers(_login(client))
    second = _headers(_login(client))

    r = client.post("/api/v1/auth/sessions/revoke-all", headers=second)
    assert r.status_code == 200 and r.json()["closed"] == 3   # включая вход регистрации
    assert client.get("/api/v1/projects", headers=first).status_code == 401
    assert client.get("/api/v1/projects", headers=second).status_code == 401


# --- Пароль ---

def test_password_change_closes_other_sessions_and_keeps_mine(client, register):
    """Пароль меняют в том числе из-за подозрения на чужой доступ — оставить чужой вход
    живым значило бы сделать смену бессмысленной. Выкидывать себя тоже незачем: человек
    только что подтвердил, что он это он."""
    register()
    other = _headers(_login(client))
    mine = _headers(_login(client))

    assert client.post("/api/v1/auth/password",
                       json={"current_password": "secret123", "new_password": "newsecret1"},
                       headers=mine).status_code == 204
    assert client.get("/api/v1/projects", headers=other).status_code == 401
    assert client.get("/api/v1/projects", headers=mine).status_code == 200


def test_failed_password_change_closes_nothing(client, register):
    headers = register()
    other = _headers(_login(client))
    client.post("/api/v1/auth/password",
                json={"current_password": "wrong-one", "new_password": "newsecret1"},
                headers=headers)
    assert client.get("/api/v1/projects", headers=other).status_code == 200


def test_password_reset_link_closes_all_previous_sessions(client, register, db_session):
    """Ссылку сброса выдают, когда доступ к учётной записи под вопросом."""
    owner = register()
    org = client.get("/api/v1/organizations", headers=owner).json()[0]["id"]
    member = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "к@e.ru", "full_name": "К", "role": "editor"},
                         headers=owner).json()
    client.post("/api/v1/auth/activate",
                json={"token": member["invite_token"], "password": "secret123"})
    old = _headers(_login(client, email="к@e.ru"))
    assert client.get("/api/v1/projects", headers=old).status_code == 200

    link = client.post(f"/api/v1/organizations/{org}/members/{member['user_id']}/access-link",
                       headers=owner).json()
    client.post("/api/v1/auth/activate",
                json={"token": link["token"], "password": "another123"})
    assert client.get("/api/v1/projects", headers=old).status_code == 401


# --- Срок жизни ---

def test_remember_me_is_a_choice_not_a_default(client, register):
    register()
    short = jwt.decode(_login(client), JWT_SECRET, algorithms=[JWT_ALG])
    long = jwt.decode(_login(client, remember=True), JWT_SECRET, algorithms=[JWT_ALG])
    assert short["exp"] - short["iat"] == JWT_TTL_SECONDS
    assert long["exp"] - long["iat"] == REMEMBER_TTL_SECONDS


def test_token_and_session_share_one_expiry(client, register, db_session):
    """Два разных срока однажды разошлись бы, и «активный» вход перестал бы работать
    без объяснения."""
    register()
    token = _login(client, remember=True)
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    session = crud.get_session(db_session, payload["jti"])
    expires = session.expires_at.replace(tzinfo=timezone.utc)
    assert abs((expires - datetime.fromtimestamp(payload["exp"], timezone.utc))
               .total_seconds()) < 5


def test_expired_session_is_refused_and_named(client, register, db_session):
    headers = register()
    session_id = next(s["id"] for s in _sessions(client, headers) if s["current"])
    session = crud.get_session(db_session, session_id)
    session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    refused = client.get("/api/v1/projects", headers=headers)
    assert refused.status_code == 401 and "истёк" in refused.json()["detail"]


# --- Токены без сеанса ---

def test_a_token_without_a_session_is_refused(client, register):
    """Токены, выпущенные до реестра, не принимаются: отозвать такой токен было бы
    нечем, и жил бы он до истечения срока — то есть ровно столько, сколько нужно тому,
    кто его унёс. Цена — один вход заново для всех; молчаливое исключение стоило бы
    дороже и навсегда."""
    headers = register()
    me = client.get("/api/v1/auth/me", headers=headers).json()
    now = int(datetime.now(timezone.utc).timestamp())
    legacy = jwt.encode({"sub": me["id"], "iat": now, "exp": now + 3600, "typ": "access"},
                        JWT_SECRET, algorithm=JWT_ALG)
    assert client.get("/api/v1/projects", headers=_headers(legacy)).status_code == 401


def test_a_token_naming_a_stranger_session_is_refused(client, register):
    """Подпись верна, но сеанс не наш — принимать нельзя: иначе `jti` был бы украшением."""
    a = register(email="a@e.ru", org="Первая")
    register(email="b@e.ru", org="Вторая")
    b_token = client.post("/api/v1/auth/login",
                          json={"email": "b@e.ru", "password": "secret123"}
                          ).json()["access_token"]
    b_session = jwt.decode(b_token, JWT_SECRET, algorithms=[JWT_ALG])["jti"]
    a_payload = jwt.decode(a["Authorization"].split()[1], JWT_SECRET, algorithms=[JWT_ALG])

    # Токен «а» с чужим jti: сеанс принадлежит «б», и запрос пойдёт от «б», а не от «а».
    forged = jwt.encode({**a_payload, "jti": b_session}, JWT_SECRET, algorithm=JWT_ALG)
    me = client.get("/api/v1/auth/me", headers=_headers(forged)).json()
    assert me["email"] == "b@e.ru"


# --- Стыки с прежними фазами ---

def test_blocked_account_still_hears_the_reason(client, db_session, register):
    """Блокировка (B2) закрывает сеансы, но причина обязана пережить механизм, который
    появился позже неё: иначе человек получил бы «сеанс завершён», пошёл входить заново
    и упёрся в ту же стену, не понимая, во что."""
    staff_headers = register(email="staff@e.ru", org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, "staff@e.ru"),
                   is_staff=True)
    owner = register(email="o@e.ru", org="Орг")
    user_id = client.get("/api/v1/auth/me", headers=owner).json()["id"]

    client.post(f"/api/v1/admin/users/{user_id}/block", json={"reason": "по заявлению"},
                headers=staff_headers)
    refused = client.get("/api/v1/projects", headers=owner)
    assert refused.status_code == 403 and "по заявлению" in refused.json()["detail"]


def test_revocations_are_written_to_the_journal(client, register):
    """Закрытие входов — событие доступа, и журнал о нём не молчит."""
    headers = register()
    org = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    other = _headers(_login(client))
    other_id = next(s["id"] for s in _sessions(client, other) if s["current"])
    client.delete(f"/api/v1/auth/sessions/{other_id}", headers=headers)
    client.post("/api/v1/auth/sessions/revoke-all", headers=headers)

    # «Выйти на всех устройствах» закрыло и этот вход — читаем журнал новым.
    actions = {e["action"] for e in
               client.get(f"/api/v1/organizations/{org}/audit-log",
                          headers=_headers(_login(client))).json()["entries"]}
    assert {"auth.session_revoke", "auth.sessions_revoke_all"} <= actions


def test_presence_mark_survives_the_session_check(client, register):
    """Отметка присутствия участника (A3) считается по-прежнему: сеанс добавил дверь,
    но не подменил собой членство."""
    headers = register()
    client.get("/api/v1/projects", headers=headers)
    org = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    me = client.get("/api/v1/auth/me", headers=headers).json()["email"]
    member = next(m for m in client.get(f"/api/v1/organizations/{org}/members",
                                        headers=headers).json() if m["email"] == me)
    assert member["last_seen_at"] is not None
