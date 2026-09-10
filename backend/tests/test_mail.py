"""Почта платформы (ADMIN-DECOMPOSITION.md, D1).

Проверяется не «умеем ли мы говорить по SMTP» — это работа стандартной библиотеки, — а
**обещания вокруг письма**: платформа не делает вид, что письма уходят, когда почта не
настроена; неудачную отправку она называет вслух; ручная ссылка не исчезает; и форма
«забыли пароль» не превращается в проверялку «есть ли у вас такой клиент».
"""
from __future__ import annotations

import pytest

from app import mail
from app.mail import Letter, invite_letter, new_device_letter, reset_letter, send


@pytest.fixture
def post(monkeypatch):
    """Включить почту «в память» на время теста."""
    monkeypatch.setenv("MAIL_BACKEND", "memory")
    monkeypatch.setenv("PUBLIC_URL", "https://finans.example")
    mail.clear_outbox()
    yield mail.outbox
    mail.clear_outbox()


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


# --- Отправка и её отсутствие ---

def test_without_configuration_nothing_is_sent_and_nothing_is_promised():
    """Главное правило фазы: выключенная почта не притворяется включённой."""
    assert mail.mail_enabled() is False
    result = send("k@e.ru", Letter("тема", "текст"))
    # «Не пытались» и «пытались, не вышло» — разные ответы, и путать их нельзя.
    assert result.attempted is False and result.ok is False
    assert "не настроена" in result.error


def test_a_broken_address_is_named_not_swallowed(post):
    result = send("не-адрес", Letter("тема", "текст"))
    assert result.ok is False and "не похож на почтовый" in result.error
    assert post() == []


def test_letters_never_carry_a_password_or_a_code(post):
    """В письмах — только одноразовые ссылки: письмо живёт в чужом ящике вечно."""
    letters = [
        invite_letter(organization="Орг", inviter="o@e.ru", token="tok"),
        reset_letter(token="tok", has_password=True),
        new_device_letter(device="Chrome · Windows", ip="203.0.113.7", when="вчера"),
    ]
    for letter in letters:
        assert "пароль:" not in letter.text.lower()
        # И каждое письмо говорит, что отвечать на него бесполезно: ящика для входящих
        # у платформы нет, а молчание в ответ читается как пренебрежение.
        assert "Отвечать на него бесполезно" in letter.text


def test_the_link_in_a_letter_is_absolute(post):
    letter = invite_letter(organization="Орг", inviter="o@e.ru", token="tok")
    assert "https://finans.example/activate?token=tok" in letter.text


# --- Приглашение ---

def test_invite_letter_goes_out_and_the_link_stays(client, register, post):
    """Почта — добавление к «передайте лично», а не замена: ссылка возвращается всё
    равно, потому что письмо может не дойти молча."""
    headers = register()
    org = _org_id(client, headers)
    body = client.post(f"/api/v1/organizations/{org}/members",
                       json={"email": "k@e.ru", "full_name": "Коллега", "role": "editor"},
                       headers=headers).json()

    assert body["mail"] == {"attempted": True, "ok": True, "error": ""}
    assert body["invite_token"]                       # ссылка на месте
    (to, letter), = post()
    assert to == "k@e.ru" and body["invite_token"] in letter.text


def test_invite_without_mail_says_it_did_not_try(client, register):
    headers = register()
    org = _org_id(client, headers)
    body = client.post(f"/api/v1/organizations/{org}/members",
                       json={"email": "k@e.ru", "full_name": "Коллега", "role": "editor"},
                       headers=headers).json()
    assert body["mail"]["attempted"] is False and body["invite_token"]


def test_a_failed_letter_is_reported_not_hidden(client, register, post, monkeypatch):
    """Письмо, потерянное молча, хуже неотправленного: администратор должен узнать,
    что передавать ссылку придётся лично."""
    monkeypatch.setattr(mail, "send",
                        lambda to, letter: mail.Sent(ok=False, error="сервер отказал"))
    headers = register()
    org = _org_id(client, headers)
    body = client.post(f"/api/v1/organizations/{org}/members",
                       json={"email": "k@e.ru", "full_name": "Коллега", "role": "editor"},
                       headers=headers).json()
    assert body["mail"]["ok"] is False and "сервер отказал" in body["mail"]["error"]
    assert body["invite_token"]

    # И это событие для журнала: «письмо не ушло» — то, с чем придут разбираться.
    entries = client.get(f"/api/v1/organizations/{org}/audit-log",
                         headers=headers).json()["entries"]
    failed = [e for e in entries if e["action"] == "member.invite_mail"]
    assert failed and "не ушло" in failed[0]["details"]


def test_access_link_is_also_sent(client, register, post):
    headers = register()
    org = _org_id(client, headers)
    invited = client.post(f"/api/v1/organizations/{org}/members",
                          json={"email": "k@e.ru", "full_name": "Коллега",
                                "role": "editor"}, headers=headers).json()
    mail.clear_outbox()

    link = client.post(
        f"/api/v1/organizations/{org}/members/{invited['user_id']}/access-link",
        headers=headers).json()
    assert link["mail"]["ok"] is True and link["token"]
    (to, letter), = post()
    assert to == "k@e.ru" and link["token"] in letter.text


# --- «Забыли пароль» ---

def test_forgot_password_is_refused_without_mail_and_names_the_way_out(client, register):
    register()
    r = client.post("/api/v1/auth/forgot-password", json={"email": "owner@e.ru"})
    assert r.status_code == 409
    assert "администратора" in r.json()["detail"]


def test_forgot_password_answers_the_same_for_a_stranger(client, register, post):
    """Разный ответ превратил бы форму в проверялку «есть ли у вас такой клиент»."""
    register()
    mine = client.post("/api/v1/auth/forgot-password", json={"email": "owner@e.ru"})
    alien = client.post("/api/v1/auth/forgot-password", json={"email": "нет@e.ru"})

    assert mine.status_code == alien.status_code == 200
    assert mine.json() == alien.json()
    # Письмо при этом ушло ровно одно — тому, кто существует.
    assert [to for to, _ in post()] == ["owner@e.ru"]


def test_forgot_password_link_actually_works(client, register, post):
    """Ссылка из письма — рабочая дорога назад, а не вежливый текст."""
    register()
    client.post("/api/v1/auth/forgot-password", json={"email": "owner@e.ru"})
    (_, letter), = post()
    token = letter.text.split("token=")[1].split()[0]

    r = client.post("/api/v1/auth/activate",
                    json={"token": token, "password": "novyi-parol7"})
    assert r.status_code == 200
    assert client.post("/api/v1/auth/login",
                       json={"email": "owner@e.ru", "password": "novyi-parol7"}
                       ).status_code == 200


def test_the_owner_finally_has_a_way_back(client, register, post):
    """Дыра, названная в C2: администратор владельцу ссылку не выдаёт (иначе заберёт
    организацию), и владелец был единственной ролью без восстановления. Свой ящик её
    закрывает — ссылка уходит **в ящик**, а не просившему."""
    register()
    r = client.post("/api/v1/auth/forgot-password", json={"email": "owner@e.ru"})
    assert r.status_code == 200 and len(post()) == 1


def test_a_blocked_account_gets_no_letter(client, register, db_session, post):
    from app import crud
    register()
    user = crud.get_user_by_email(db_session, "owner@e.ru")
    crud.set_user_block(db_session, user, blocked=True, by="платформа",
                        reason="проверка")

    r = client.post("/api/v1/auth/forgot-password", json={"email": "owner@e.ru"})
    # Ответ тот же самый — блокировка не повод рассказать о ней всякому спросившему.
    assert r.status_code == 200 and post() == []


def test_letters_to_one_account_are_limited(client, register, post, monkeypatch):
    """Письмо уходит владельцу ящика: ограничение по адресу клиента значило бы, что
    завалить чужой ящик можно с десяти адресов."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    register()
    for _ in range(5):
        r = client.post("/api/v1/auth/forgot-password", json={"email": "owner@e.ru"})
        assert r.status_code == 200          # ответ **не меняется** при превышении
    assert len(post()) == 3


def test_the_request_is_written_to_the_journal(client, register, post):
    headers = register()
    org = _org_id(client, headers)
    client.post("/api/v1/auth/forgot-password", json={"email": "owner@e.ru"})

    actions = {e["action"] for e in
               client.get(f"/api/v1/organizations/{org}/audit-log",
                          headers=headers).json()["entries"]}
    assert "auth.password_reset_requested" in actions


# --- Второй фактор и ссылка сброса ---

def test_the_reset_link_does_not_bypass_the_second_factor(client, register, db_session,
                                                          post):
    """Иначе второй фактор выключался бы первым же письмом: доступ к ящику означал бы
    вход без кода из приложения."""
    from app import crud, totp
    headers = register()
    secret = client.post("/api/v1/auth/totp/setup", headers=headers).json()["secret"]
    client.post("/api/v1/auth/totp/enable", json={"code": totp.code_at(secret)},
                headers=headers)

    client.post("/api/v1/auth/forgot-password", json={"email": "owner@e.ru"})
    (_, letter), = post()
    token = letter.text.split("token=")[1].split()[0]

    refused = client.post("/api/v1/auth/activate",
                          json={"token": token, "password": "novyi-parol7"})
    assert refused.status_code == 428             # «нужен код», а не «вы не вошли»

    user = crud.get_user_by_email(db_session, "owner@e.ru")
    ok = client.post("/api/v1/auth/activate",
                     json={"token": token, "password": "novyi-parol7",
                           "totp_code": totp.code_at(user.totp_secret)})
    assert ok.status_code == 200


# --- Вход с нового устройства ---

def test_a_new_device_is_reported_by_letter(client, register, post):
    """Обещание, отложенное в C2 до появления почты."""
    register()
    mail.clear_outbox()
    client.post("/api/v1/auth/login", json={"email": "owner@e.ru", "password": "secret123"},
                headers={"user-agent": "Mozilla/5.0 (iPhone) Safari/605"})

    (to, letter), = post()
    assert to == "owner@e.ru" and "нового устройства" in letter.subject
    # Подпись браузера — подсказка, а не удостоверение, и письмо говорит это словами.
    assert "подсказка, а не доказательство" in letter.text


def test_a_familiar_device_is_silent(client, register, post):
    """Письмо на каждый вход — это письмо, которое перестают читать."""
    register()
    mail.clear_outbox()
    client.post("/api/v1/auth/login",
                json={"email": "owner@e.ru", "password": "secret123"})
    assert post() == []


def test_the_first_login_ever_is_not_a_new_device(client, post):
    """Регистрация — не повод сообщать человеку, что он только что зарегистрировался."""
    client.post("/api/v1/auth/register",
                json={"email": "new@e.ru", "full_name": "Н", "password": "secret123",
                      "organization_name": "Орг"})
    assert post() == []


def test_a_dead_mail_server_does_not_break_the_login(client, register, monkeypatch, post):
    """Ронять вход из-за чужого сервера нельзя — тот же довод, что у проверки паролей."""
    monkeypatch.setattr(mail, "send",
                        lambda to, letter: mail.Sent(ok=False, error="таймаут"))
    register()
    r = client.post("/api/v1/auth/login",
                    json={"email": "owner@e.ru", "password": "secret123"},
                    headers={"user-agent": "Mozilla/5.0 (iPhone) Safari/605"})
    assert r.status_code == 200 and r.json()["access_token"]


# --- Что видно экрану ---

def test_capabilities_tell_the_screen_whether_mail_works(client, post):
    assert client.get("/api/v1/auth/capabilities").json() == {"mail": True}


def test_capabilities_without_mail(client):
    # «Забыли пароль?», нарисованная там, где письма не уходят, ведёт в тупик.
    assert client.get("/api/v1/auth/capabilities").json() == {"mail": False}
