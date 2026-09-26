"""Подтверждение адреса почты (OPEN-DECISIONS §4).

Механизма было два, и их смешали: подтверждение адреса **не требует ящика для входящих**
— письмо со ссылкой уходит, человек переходит, адрес подтверждён. Ящик нужен только для
обработки отказов доставки, и это отдельное решение эксплуатации.

Проверяется граница, а не механика: подтверждение **ничего не запирает**, информационные
письма на неподтверждённый адрес не уходят, дверные уходят всегда, а ссылка подтверждает
адрес только тогда, когда она **ушла в ящик** и достать её было больше неоткуда.
"""
from __future__ import annotations

from app import crud, mail
from app.db_models import AuditLogEntry
from app.notify import UNVERIFIED_DETAIL
from app.security import create_invite_token, create_verify_token, token_was_emailed


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _mail_on(monkeypatch) -> None:
    monkeypatch.setenv("MAIL_BACKEND", "memory")
    monkeypatch.setenv("PUBLIC_URL", "https://finans.example")
    mail.clear_outbox()


def _user(db, email="owner@e.ru"):
    return crud.get_user_by_email(db, email)


# --- Что подтверждение значит и чего не значит ---

def test_a_fresh_account_is_unverified_and_that_is_not_an_accusation(client, register):
    """До появления поля не подтверждал никто, и записать им «подтверждено» значило бы
    выдать догадку за факт."""
    headers = register()
    body = client.get("/api/v1/auth/email-verification", headers=headers).json()
    assert body["verified"] is False
    # Рядом сказано, что именно из-за этого не приходит, — и что вход это не затрагивает.
    assert "не уходят" in body["note"] and "восстановления пароля" in body["note"]


def test_an_unverified_address_does_not_lock_anyone_out(client, register):
    """Подтверждение ничего не запирает: иначе опечатка в адресе (и выключенная почта)
    оставляли бы человека снаружи навсегда."""
    headers = register()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    model = client.get("/api/v1/sample").json()
    assert client.post("/api/v1/projects", json={"name": "П", "model": model},
                       headers=headers).status_code == 201


def test_the_link_from_the_letter_verifies_the_address(client, register, monkeypatch,
                                                       db_session):
    _mail_on(monkeypatch)
    headers = register()
    assert client.post("/api/v1/auth/email-verification", headers=headers).json() == {
        "verified": False, "sent": True,
        "note": client.get("/api/v1/auth/email-verification",
                           headers=headers).json()["note"]}
    (to, letter), = mail.outbox()
    assert to == "owner@e.ru" and "/verify-email?token=" in letter.text

    token = letter.text.split("/verify-email?token=")[1].split("\n")[0]
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).json() == {
        "verified": True, "sent": False, "note": "Адрес подтверждён: уведомления приходят."}
    assert _user(db_session).email_verified_at is not None


def test_verification_needs_no_login_because_the_link_came_from_the_mailbox(
        client, register, monkeypatch):
    """Заставлять человека сначала войти значило бы отправить его искать пароль ради
    того, что он уже доказал переходом по ссылке."""
    _mail_on(monkeypatch)
    headers = register()
    client.post("/api/v1/auth/email-verification", headers=headers)
    (_, letter), = mail.outbox()
    token = letter.text.split("/verify-email?token=")[1].split("\n")[0]

    # Заголовка сессии нет вовсе — и это работает.
    assert client.post("/api/v1/auth/verify-email",
                       json={"token": token}).status_code == 200


def test_a_verify_token_cannot_set_a_password(client, register, db_session):
    """Отдельный тип токена, а не переиспользование приглашения: письмо «подтвердите
    адрес», которым можно задать пароль, было бы приглашением под чужим именем."""
    register()
    token = create_verify_token(_user(db_session).id)
    refused = client.post("/api/v1/auth/activate",
                          json={"token": token, "password": "chuzhoi-parol7"})
    assert refused.status_code == 400


def test_a_made_up_link_is_refused(client, register):
    register()
    r = client.post("/api/v1/auth/verify-email", json={"token": "мусор"})
    assert r.status_code == 400 and "недействительна" in r.json()["detail"]


def test_confirming_twice_keeps_the_first_date(client, register, db_session):
    """«Подтверждён 3 марта» — факт о первом доказательстве; переписывать его каждым
    письмом значило бы его терять."""
    register()
    user = _user(db_session)
    crud.mark_email_verified(db_session, user)
    first = user.email_verified_at
    crud.mark_email_verified(db_session, user)
    assert user.email_verified_at == first


# --- Ссылка подтверждает адрес, только если ушла в ящик ---

def test_only_a_link_that_went_to_the_mailbox_proves_anything():
    """Администратор вправе передать ту же ссылку лично — мессенджером, голосом, на
    бумаге. Тогда про ящик она не доказывает ничего, и признак в **подписанном** токене
    их различает: в параметре запроса его можно было бы дописать."""
    assert token_was_emailed(create_invite_token("u", emailed=True)) is True
    assert token_was_emailed(create_invite_token("u")) is False
    assert token_was_emailed("подделка") is False


def test_the_admin_link_and_the_letter_carry_different_tokens(client, register,
                                                              monkeypatch):
    """Один токен на оба канала подтверждал бы адрес у того, кто получил ссылку в
    мессенджере: письмо всего лишь дошло до сервера, а достали ссылку не оттуда."""
    _mail_on(monkeypatch)
    headers = register()
    org = _org_id(client, headers)
    body = client.post(f"/api/v1/organizations/{org}/members",
                       json={"email": "k@e.ru", "full_name": "К", "role": "editor"},
                       headers=headers).json()
    (_, letter), = mail.outbox()
    assert body["invite_token"] not in letter.text
    assert token_was_emailed(body["invite_token"]) is False


def test_activating_by_the_emailed_link_verifies_the_address(client, register,
                                                             monkeypatch, db_session):
    _mail_on(monkeypatch)
    headers = register()
    org = _org_id(client, headers)
    client.post(f"/api/v1/organizations/{org}/members",
                json={"email": "k@e.ru", "full_name": "К", "role": "editor"},
                headers=headers)
    (_, letter), = mail.outbox()
    token = letter.text.split("/activate?token=")[1].split("\n")[0]

    client.post("/api/v1/auth/activate",
                json={"token": token, "password": "kollega-parol7"})
    assert _user(db_session, "k@e.ru").email_verified_at is not None


def test_activating_by_the_hand_delivered_link_verifies_nothing(client, register,
                                                                db_session):
    """Почта выключена — администратор передал ссылку лично. Про ящик не доказано ничего,
    и записывать обратное нельзя."""
    headers = register()
    org = _org_id(client, headers)
    body = client.post(f"/api/v1/organizations/{org}/members",
                       json={"email": "k@e.ru", "full_name": "К", "role": "editor"},
                       headers=headers).json()
    client.post("/api/v1/auth/activate",
                json={"token": body["invite_token"], "password": "kollega-parol7"})
    assert _user(db_session, "k@e.ru").email_verified_at is None


# --- Какие письма уходят, а какие нет ---

def test_an_informational_letter_does_not_go_to_an_unverified_address(
        client, register, monkeypatch, db_session):
    """Чужая активность в чужом ящике — утечка, и опечатка в адресе делает её
    ежедневной."""
    _mail_on(monkeypatch)
    register()
    client.post("/api/v1/auth/login",
                json={"email": "owner@e.ru", "password": "secret123"},
                headers={"user-agent": "Mozilla/5.0 (iPhone) Safari/605"})
    assert mail.outbox() == []

    # И отказ **записан**: молчание здесь читалось бы как «письмо ушло», и администратор
    # искал бы его в спаме вместо того, чтобы попросить подтвердить адрес.
    details = [e.details for e in db_session.query(AuditLogEntry).all()]
    assert any(UNVERIFIED_DETAIL in (d or "") for d in details), details


def test_the_same_letter_goes_once_the_address_is_verified(client, register, monkeypatch,
                                                           db_session):
    _mail_on(monkeypatch)
    register()
    crud.mark_email_verified(db_session, _user(db_session))
    mail.clear_outbox()
    client.post("/api/v1/auth/login",
                json={"email": "owner@e.ru", "password": "secret123"},
                headers={"user-agent": "Mozilla/5.0 (iPhone) Safari/605"})
    (to, letter), = mail.outbox()
    assert to == "owner@e.ru" and "нового устройства" in letter.subject


def test_door_letters_go_to_an_unverified_address(client, register, monkeypatch):
    """Дверные письма — единственный способ войти. Запереть их значило бы запереть
    человека: самостоятельно зарегистрировавшийся владелец с неподтверждённым адресом
    забыл бы пароль и остался снаружи навсегда."""
    _mail_on(monkeypatch)
    register()
    mail.clear_outbox()
    client.post("/api/v1/auth/forgot-password", json={"email": "owner@e.ru"})
    (to, letter), = mail.outbox()
    assert to == "owner@e.ru" and "Восстановление пароля" in letter.subject


def _letter_builders() -> dict[str, object]:
    """Все сборщики писем продукта, **где бы они ни жили**.

    Первая версия перечня смотрела в один `mail.py` — и мимо неё уже прошли два письма об
    обсуждениях: они живут в своём роутере, рядом со своим текстом. Перечень, который
    видит не все письма, отвечает не на тот вопрос, который задаёт его имя.
    """
    import importlib
    import inspect
    import pkgutil

    import app

    found: dict[str, object] = {}
    for module in pkgutil.walk_packages(app.__path__, prefix="app."):
        loaded = importlib.import_module(module.name)
        for name, obj in vars(loaded).items():
            if (name.endswith("_letter") and inspect.isfunction(obj)
                    and obj.__module__ == loaded.__name__):
                found[f"{loaded.__name__}.{name}"] = obj
    return found


def test_every_letter_declares_whether_it_is_informational():
    """Перечень-тест: следующее информационное письмо допишут — и тут же увидят поле.
    Флаг в чужом вызове забыли бы, и рассказ о чужой активности поехал бы в чужой ящик."""
    import inspect

    builders = _letter_builders()
    assert len(builders) >= 6, "письма перестали собираться функциями *_letter?"
    informational = {name for name, obj in builders.items()
                     if "informational=True" in inspect.getsource(obj)}
    # Информационные — рассказ о чужой активности: вход с нового устройства и обе
    # разновидности письма об обсуждении. Остальные дверные: ими входят.
    assert informational == {"app.mail.new_device_letter",
                             "app.routers.comments._mention_letter",
                             "app.routers.comments._reply_letter"}


def test_every_letter_about_a_discussion_says_how_to_stop_them():
    """Письмо без выхода — рассылка (OPEN-DECISIONS §5). Проверяется не текст ссылки, а
    то, что выход **назван**: без ``PUBLIC_URL`` ссылка вела бы в никуда, и остаётся
    второй путь — выключатель в профиле."""
    from app.routers.comments import _mention_letter, _reply_letter

    for build in (_mention_letter, _reply_letter):
        with_link = build(author="a@e.ru", subject_name="П", where="", body="б",
                          link="", mute_link="https://f.example/comments/unsubscribe?"
                                             "token=t")
        assert "https://f.example/comments/unsubscribe?token=t" in with_link.text
        assert "в профиле" in with_link.text

        without = build(author="a@e.ru", subject_name="П", where="", body="б",
                        link="", mute_link="")
        assert "в профиле" in without.text


# --- Отказы называют причину ---

def test_without_mail_the_route_refuses_and_says_why(client, register):
    """Строчка «письмо отправлено», за которой ничего не происходит, уже стоила
    приглашённым нескольких дней ожидания (D1)."""
    headers = register()
    r = client.post("/api/v1/auth/email-verification", headers=headers)
    assert r.status_code == 409
    assert "не настроена" in r.json()["detail"]
    # И названо, что от этого ничего не теряется: уведомления и так никому не уходят.
    assert "не уходят никому" in r.json()["detail"]


def test_asking_again_when_already_verified_sends_nothing(client, register, monkeypatch,
                                                          db_session):
    _mail_on(monkeypatch)
    headers = register()
    crud.mark_email_verified(db_session, _user(db_session))
    mail.clear_outbox()
    body = client.post("/api/v1/auth/email-verification", headers=headers).json()
    assert body == {"verified": True, "sent": False,
                    "note": "Адрес подтверждён: уведомления приходят."}
    assert mail.outbox() == []


def test_the_letter_is_not_sent_over_and_over(client, register, monkeypatch):
    """Кнопка «прислать ещё раз» без ограничения — способ завалить чужой ящик."""
    _mail_on(monkeypatch)
    headers = register()
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    for _ in range(3):
        client.post("/api/v1/auth/email-verification", headers=headers)
    r = client.post("/api/v1/auth/email-verification", headers=headers)
    assert r.status_code == 429 and "уже отправляли" in r.json()["detail"]
