"""Письма об обсуждениях: подписка на ветку вместо дайджеста (OPEN-DECISIONS §5).

Дайджест «что произошло за день» перестают читать на второй неделе и он требует решений
о времени, часовом поясе и составе. Вопрос, который человек задаёт на самом деле, —
**«мне ответили?»**, и отвечает на него подписка на ветку.

Проверяются обещания, а не механика: подписан тот, кто участвует; письмо одно и тишина;
отписка есть в самом письме и переживает перезапуск; отписка **не глотает обращение по
имени** — и это сказано там же, где отписываются; общий выключатель гасит всё.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import crud, mail
from app.comments import NOTIFY_PAUSE, ThreadState, reply_targets, thread_participants
from app.security import create_thread_mute_token


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _project(client, headers, name="Проект") -> str:
    model = client.get("/api/v1/sample").json()
    return client.post("/api/v1/projects", json={"name": name, "model": model},
                       headers=headers).json()["id"]


def _member(client, owner, db, email="k@e.ru", role="editor") -> dict:
    """Участник **с подтверждённым адресом**: письма об обсуждениях информационные, и на
    неподтверждённый адрес не уходят вовсе (D1)."""
    org = _org_id(client, owner)
    invite = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": email, "full_name": "Коллега", "role": role},
                         headers=owner).json()
    crud.mark_email_verified(db, crud.get_user_by_email(db, email))
    token = client.post("/api/v1/auth/activate",
                        json={"token": invite["invite_token"],
                              "password": "kollega-parol7"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _say(client, headers, pid, text, anchor="", label=""):
    return client.post(f"/api/v1/projects/{pid}/comments",
                       json={"body": text, "anchor": anchor, "anchor_label": label},
                       headers=headers)


def _mail_on(monkeypatch) -> None:
    monkeypatch.setenv("MAIL_BACKEND", "memory")
    monkeypatch.setenv("PUBLIC_URL", "https://finans.example")
    mail.clear_outbox()


def _to(address: str) -> list:
    return [letter for to, letter in mail.outbox() if to == address]


# --- Кто подписан ---

def test_participation_is_read_from_the_thread_not_stored_as_a_list():
    """Отдельный список подписчиков — вторая правда: он отстал бы от разговора при первой
    же реплике, написанной мимо экрана."""
    class Row:
        def __init__(self, author, mentions=""):
            self.author_email, self.mentions = author, mentions

    rows = [Row("a@e.ru", "b@e.ru,c@e.ru"), Row("b@e.ru"), Row("A@E.ru")]
    # Порядок — по первому появлению, повтор в другом регистре не удваивает человека.
    assert thread_participants(rows) == ["a@e.ru", "b@e.ru", "c@e.ru"]


def test_the_author_is_not_written_to_about_their_own_words():
    now = datetime.now(timezone.utc)
    targets = reply_targets(["a@e.ru", "b@e.ru"], author_email="A@e.ru", mentioned=[],
                            members=["a@e.ru", "b@e.ru"], state={}, now=now)
    assert targets == ["b@e.ru"]


def test_someone_called_by_name_does_not_also_get_the_follow_up_letter():
    """Два письма об одной реплике — ровно та рассылка, против которой пауза и написана."""
    now = datetime.now(timezone.utc)
    targets = reply_targets(["b@e.ru", "c@e.ru"], author_email="a@e.ru",
                            mentioned=["B@e.ru"], members=["b@e.ru", "c@e.ru"],
                            state={}, now=now)
    assert targets == ["c@e.ru"]


def test_a_participant_who_left_the_organization_gets_nothing():
    """Участник ветки мог уйти из компании, а разговор о её делах остался: письмо о нём
    наружу не уезжает."""
    now = datetime.now(timezone.utc)
    targets = reply_targets(["b@e.ru", "ushel@e.ru"], author_email="a@e.ru", mentioned=[],
                            members=["a@e.ru", "b@e.ru"], state={}, now=now)
    assert targets == ["b@e.ru"]


# --- Пауза ---

def test_one_letter_and_silence_not_a_letter_per_reply():
    now = datetime.now(timezone.utc)
    state = {"b@e.ru": ThreadState(last_notified=now - timedelta(minutes=5))}
    assert reply_targets(["b@e.ru"], author_email="a@e.ru", mentioned=[],
                         members=["b@e.ru"], state=state, now=now) == []


def test_after_the_pause_the_letter_comes_again():
    now = datetime.now(timezone.utc)
    state = {"b@e.ru": ThreadState(last_notified=now - NOTIFY_PAUSE - timedelta(minutes=1))}
    assert reply_targets(["b@e.ru"], author_email="a@e.ru", mentioned=[],
                         members=["b@e.ru"], state=state, now=now) == ["b@e.ru"]


def test_never_written_to_is_not_written_to_long_ago():
    """``None`` здесь значит «не писали», а не «писали давно»: перепутать их — значит
    промолчать в первый же раз, когда письмо и нужно."""
    now = datetime.now(timezone.utc)
    assert reply_targets(["b@e.ru"], author_email="a@e.ru", mentioned=[],
                         members=["b@e.ru"], state={"b@e.ru": ThreadState()},
                         now=now) == ["b@e.ru"]


def test_naive_time_from_sqlite_does_not_crash_the_reply(monkeypatch):
    """SQLite отдаёт время без пояса. Упасть из-за этого посреди отправленной реплики —
    худший исход: реплика уже записана, а человек видит ошибку."""
    now = datetime.now(timezone.utc)
    state = {"b@e.ru": ThreadState(last_notified=(now - timedelta(minutes=5))
                                   .replace(tzinfo=None))}
    assert reply_targets(["b@e.ru"], author_email="a@e.ru", mentioned=[],
                         members=["b@e.ru"], state=state, now=now) == []


# --- Через продукт ---

def test_a_participant_is_told_about_a_reply(client, register, monkeypatch, db_session):
    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    colleague = _member(client, owner, db_session)
    _say(client, colleague, pid, "Откуда такая себестоимость?",
         anchor="line:income:I5", label="Себестоимость (I5)")
    mail.clear_outbox()

    body = _say(client, owner, pid, "Из прайса поставщика", anchor="line:income:I5",
                label="Себестоимость (I5)").json()
    assert body["followed"] == ["k@e.ru"]
    (letter,), = [_to("k@e.ru")]
    # Текст реплики внутри: иначе письмо заставляет открыть систему, чтобы узнать,
    # стоило ли её открывать.
    assert "Из прайса поставщика" in letter.text and "Себестоимость (I5)" in letter.text
    # И письмо называет свою паузу: тишина иначе читается как «больше никто не ответил».
    assert "ближайший час" in letter.text


def test_the_pause_holds_across_a_restart(client, register, monkeypatch, db_session):
    """Ограничитель в памяти процесса обнулился бы на выкатке, и получатель узнал бы об
    этом тремя письмами подряд."""
    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    colleague = _member(client, owner, db_session)
    _say(client, colleague, pid, "Вопрос")
    mail.clear_outbox()

    assert _say(client, owner, pid, "Ответ").json()["followed"] == ["k@e.ru"]
    assert len(_to("k@e.ru")) == 1
    # Вторая и третья реплика в тот же час письма не дают — и ответ об этом не врёт.
    assert _say(client, owner, pid, "И ещё").json()["followed"] == []
    assert _say(client, owner, pid, "И вот").json()["followed"] == []
    assert len(_to("k@e.ru")) == 1

    # Пауза живёт в базе, а не в процессе: отодвинем отметку — письмо приходит снова.
    user = crud.get_user_by_email(db_session, "k@e.ru")
    row = crud.get_comment_subscription(db_session, user.id, "project", pid, "")
    row.last_notified_at = datetime.now(timezone.utc) - NOTIFY_PAUSE - timedelta(minutes=1)
    db_session.commit()
    assert _say(client, owner, pid, "Ещё через час").json()["followed"] == ["k@e.ru"]
    assert len(_to("k@e.ru")) == 2


def test_a_mention_and_a_reply_do_not_make_two_letters_about_one_thread(
        client, register, monkeypatch, db_session):
    """«Позвали, а через минуту ответили» — одна очередь реплик, а не два повода писать."""
    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    _member(client, owner, db_session)
    mail.clear_outbox()

    _say(client, owner, pid, "@k@e.ru глянь")
    assert len(_to("k@e.ru")) == 1
    assert _say(client, owner, pid, "и ещё вот тут").json()["followed"] == []
    assert len(_to("k@e.ru")) == 1


def test_threads_are_counted_separately(client, register, monkeypatch, db_session):
    """Обсуждение строки I5 и обсуждение вкладки «Сбыт» — разные разговоры: пауза в одном
    не затыкает другой."""
    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    colleague = _member(client, owner, db_session)
    _say(client, colleague, pid, "Вопрос про I5", anchor="line:income:I5")
    _say(client, colleague, pid, "Вопрос про сбыт", anchor="tab:sales")
    mail.clear_outbox()

    assert _say(client, owner, pid, "Ответ", anchor="line:income:I5") \
        .json()["followed"] == ["k@e.ru"]
    assert _say(client, owner, pid, "Ответ", anchor="tab:sales") \
        .json()["followed"] == ["k@e.ru"]
    assert len(_to("k@e.ru")) == 2


# --- Отписка ---

def test_unsubscribing_stops_the_follow_up_letters(client, register, monkeypatch,
                                                   db_session):
    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    colleague = _member(client, owner, db_session)
    _say(client, colleague, pid, "Вопрос")
    mail.clear_outbox()

    state = client.post("/api/v1/comments/subscription",
                        json={"subject_type": "project", "subject_id": pid, "anchor": "",
                              "muted": True}, headers=colleague).json()
    assert state["muted"] is True
    # Рядом с отпиской сказано, чего она **не** остановит: обещание, которое человек
    # проверит именно здесь.
    assert "по имени" in state["note"]

    assert _say(client, owner, pid, "Ответ").json()["followed"] == []
    assert _to("k@e.ru") == []


def test_a_direct_call_by_name_still_arrives_after_unsubscribing(
        client, register, monkeypatch, db_session):
    """Проглотить прямое обращение значило бы обмануть обоих: позвавший ждёт, позванный
    не придёт. Поэтому отписка глушит слежение за веткой, а не зов по имени, — и говорит
    об этом и в ответе, и в письме."""
    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    colleague = _member(client, owner, db_session)
    client.post("/api/v1/comments/subscription",
                json={"subject_type": "project", "subject_id": pid, "muted": True},
                headers=colleague)
    mail.clear_outbox()

    assert _say(client, owner, pid, "@k@e.ru это важно").json()["notified"] == ["k@e.ru"]
    (letter,) = _to("k@e.ru")
    assert "не остановит" in letter.text


def test_the_link_from_the_letter_unsubscribes_without_logging_in(
        client, register, monkeypatch, db_session):
    """Требовать пароль ради «перестаньте мне писать» — способ получить жалобу на спам
    вместо отписки."""
    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    colleague = _member(client, owner, db_session)
    _say(client, colleague, pid, "Вопрос")
    mail.clear_outbox()
    _say(client, owner, pid, "Ответ")
    (letter,) = _to("k@e.ru")

    token = letter.text.split("/comments/unsubscribe?token=")[1].split("\n")[0]
    # Заголовка сессии нет вовсе — и это работает.
    r = client.post("/api/v1/comments/unsubscribe", json={"token": token})
    assert r.status_code == 200 and r.json()["muted"] is True

    user = crud.get_user_by_email(db_session, "k@e.ru")
    row = crud.get_comment_subscription(db_session, user.id, "project", pid, "")
    assert row.muted_at is not None


def test_unsubscribing_has_a_way_back(client, register, monkeypatch, db_session):
    """Отписка, из которой нет дороги назад, — ловушка: её нажимают один раз на всю
    жизнь."""
    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    colleague = _member(client, owner, db_session)
    token = create_thread_mute_token(
        crud.get_user_by_email(db_session, "k@e.ru").id, "project", pid, "")
    client.post("/api/v1/comments/unsubscribe", json={"token": token})

    back = client.post("/api/v1/comments/unsubscribe",
                       json={"token": token, "muted": False}).json()
    assert back["muted"] is False
    _say(client, colleague, pid, "Вопрос")
    mail.clear_outbox()
    assert _say(client, owner, pid, "Ответ").json()["followed"] == ["k@e.ru"]


def test_a_forged_link_changes_nothing_and_says_where_to_go(client, register):
    register()
    r = client.post("/api/v1/comments/unsubscribe", json={"token": "мусор"})
    assert r.status_code == 400
    # Отказ называет второй путь: «ссылка устарела» без выхода — это тупик.
    assert "в профиле" in r.json()["detail"]


def test_the_thread_comes_from_the_signed_token_not_the_request(client, register,
                                                                db_session):
    """Ветку в теле запроса можно было бы переписать и отписать человека от чужого
    разговора."""
    owner = register()
    mine = _project(client, owner, "Мой")
    other = _project(client, owner, "Чужой")
    user = crud.get_user_by_email(db_session, "owner@e.ru")
    client.post("/api/v1/comments/unsubscribe",
                json={"token": create_thread_mute_token(user.id, "project", mine, ""),
                      "subject_id": other})

    assert crud.get_comment_subscription(db_session, user.id, "project", other, "") is None
    assert crud.get_comment_subscription(db_session, user.id, "project", mine, "") \
        is not None


def test_unsubscribing_is_never_a_get(client):
    """Почтовые фильтры организаций ходят по ссылкам из писем заранее: отписка по ``GET``
    срабатывала бы у тех, кто её не нажимал, — молча и без их ведома."""
    from app.main import app

    schema = app.openapi()["paths"]["/api/v1/comments/unsubscribe"]
    assert set(schema) == {"post"}


# --- Общий выключатель ---

def test_the_profile_switch_silences_everything_including_a_call_by_name(
        client, register, monkeypatch, db_session):
    """Это последний рубеж «не пишите мне», и щель в нём сделала бы его неправдой."""
    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    colleague = _member(client, owner, db_session)
    profile = client.patch("/api/v1/auth/me",
                           json={"full_name": "Коллега", "comment_emails": False},
                           headers=colleague).json()
    assert profile["comment_emails"] is False
    mail.clear_outbox()

    # Зов по имени — тоже письмо об обсуждении, и выключатель гасит его. Проверяется
    # **сразу**: если ждать реплики следом, молчание объяснит уже пауза, и настоящая
    # причина останется непроверенной.
    _say(client, owner, pid, "@k@e.ru это важно")
    assert _to("k@e.ru") == []

    _say(client, colleague, pid, "участвую")
    _say(client, owner, pid, "ответ")
    assert _to("k@e.ru") == []


def test_editing_the_name_does_not_switch_letters_back_on(client, register):
    headers = register()
    client.patch("/api/v1/auth/me", json={"full_name": "Имя", "comment_emails": False},
                 headers=headers)
    client.patch("/api/v1/auth/me", json={"full_name": "Другое имя"}, headers=headers)
    assert client.get("/api/v1/auth/me", headers=headers).json()["comment_emails"] is False


# --- Границы ---

def test_without_mail_nothing_is_sent_but_the_answer_still_says_who_was_called(
        client, register, db_session):
    """«Кому бы ушло» — часть смысла ответа: где почта выключена, автор обязан узнать,
    кого позвать самому."""
    owner = register()
    pid = _project(client, owner)
    colleague = _member(client, owner, db_session)
    _say(client, colleague, pid, "Вопрос")
    body = _say(client, owner, pid, "Ответ").json()
    assert body["followed"] == ["k@e.ru"] and body["mail"]["attempted"] is False


def test_an_unverified_address_still_gets_no_informational_letter(client, register,
                                                                  monkeypatch, db_session):
    """Письмо о реплике — рассказ о чужой активности: на неподтверждённый адрес оно не
    уходит (обещание подтверждения адреса пережило и этот механизм)."""
    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    org = _org_id(client, owner)
    invite = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "k@e.ru", "full_name": "К", "role": "editor"},
                         headers=owner).json()
    token = client.post("/api/v1/auth/activate",
                        json={"token": invite["invite_token"],
                              "password": "kollega-parol7"}).json()["access_token"]
    _say(client, {"Authorization": f"Bearer {token}"}, pid, "Вопрос")
    mail.clear_outbox()

    assert _say(client, owner, pid, "Ответ").json()["followed"] == ["k@e.ru"]
    assert _to("k@e.ru") == []


def test_a_case_discussion_works_the_same_way(client, register, monkeypatch, db_session):
    """У проекта и у дела обсуждение устроено одинаково — вторая копия правил разошлась бы
    с первой."""
    _mail_on(monkeypatch)
    owner = register()
    colleague = _member(client, owner, db_session)
    cid = client.post("/api/v1/audit/subjects",
                      json={"name": "Дело",
                            "model": {"name": "Дело", "periods": [], "lines": []}},
                      headers=owner).json()["id"]
    client.post(f"/api/v1/audit/subjects/{cid}/comments", json={"body": "Вопрос"},
                headers=colleague)
    mail.clear_outbox()

    body = client.post(f"/api/v1/audit/subjects/{cid}/comments", json={"body": "Ответ"},
                       headers=owner).json()
    assert body["followed"] == ["k@e.ru"] and len(_to("k@e.ru")) == 1


def test_the_outcome_of_the_letter_reaches_the_journal(client, register, monkeypatch,
                                                       db_session):
    """Письмо, потерянное молча, хуже неотправленного: исход пишется в журнал теми же
    словами, какими вернулся из отправки."""
    from app.db_models import AuditLogEntry

    _mail_on(monkeypatch)
    owner = register()
    pid = _project(client, owner)
    colleague = _member(client, owner, db_session)
    _say(client, colleague, pid, "Вопрос")
    _say(client, owner, pid, "Ответ")

    actions = [e.action for e in db_session.query(AuditLogEntry).all()]
    assert "comment.reply_mail" in actions
