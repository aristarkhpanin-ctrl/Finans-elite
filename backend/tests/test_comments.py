"""Обсуждение рядом с числами (ADMIN-DECOMPOSITION.md, D3).

Проверяются обещания, а не механика хранения: реплика привязана к месту и остаётся
понятной после правок модели, упоминание зовёт, но не открывает доступ, нераспознанное
упоминание названо, удалённая реплика говорит о себе, а правки текста нет вовсе.
"""
from __future__ import annotations

from app import crud, mail
from app.comments import parse_mentions


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _project(client, headers, name="Проект") -> str:
    model = client.get("/api/v1/sample").json()
    return client.post("/api/v1/projects", json={"name": name, "model": model},
                       headers=headers).json()["id"]


def _case(client, headers, name="Дело") -> str:
    return client.post("/api/v1/audit/subjects",
                       json={"name": name,
                             "model": {"name": name, "periods": [], "lines": []}},
                       headers=headers).json()["id"]


def _member(client, owner, email="k@e.ru", role="viewer") -> dict:
    org = _org_id(client, owner)
    return client.post(f"/api/v1/organizations/{org}/members",
                       json={"email": email, "full_name": "Коллега", "role": role},
                       headers=owner).json()


def _activate(client, invite, password="kollega-parol7") -> dict:
    token = client.post("/api/v1/auth/activate",
                        json={"token": invite["invite_token"],
                              "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _say(client, headers, pid, text, anchor="", label=""):
    return client.post(f"/api/v1/projects/{pid}/comments",
                       json={"body": text, "anchor": anchor, "anchor_label": label},
                       headers=headers)


# --- Место обсуждения ---

def test_a_comment_remembers_the_place_it_was_written_about(client, register):
    """«Обсуждение проекта» — это чат, из которого через месяц не понять, о какой строке
    шла речь."""
    headers = register()
    pid = _project(client, headers)
    _say(client, headers, pid, "Откуда такая себестоимость?",
         anchor="line:income:I5", label="Себестоимость продаж (I5)")

    rows = client.get(f"/api/v1/projects/{pid}/comments", headers=headers).json()
    assert rows[0]["anchor"] == "line:income:I5"
    assert rows[0]["anchor_label"] == "Себестоимость продаж (I5)"


def test_the_label_survives_the_model_change(client, register):
    """Подпись места хранится **на момент написания**: объект переименуют, а разговор
    обязан остаться понятным."""
    headers = register()
    pid = _project(client, headers)
    _say(client, headers, pid, "Проверить норму", anchor="product:p1",
         label="Продукт «Ромашка»")

    project = client.get(f"/api/v1/projects/{pid}", headers=headers).json()
    project["model"]["header"]["project_name"] = "Другое имя"
    client.put(f"/api/v1/projects/{pid}",
               json={"model": project["model"]}, headers=headers)

    rows = client.get(f"/api/v1/projects/{pid}/comments", headers=headers).json()
    assert rows[0]["anchor_label"] == "Продукт «Ромашка»"


def test_comments_can_be_narrowed_to_one_place(client, register):
    headers = register()
    pid = _project(client, headers)
    _say(client, headers, pid, "К сбыту", anchor="tab:sales", label="Сбыт")
    _say(client, headers, pid, "К активам", anchor="tab:assets", label="Активы")

    rows = client.get(f"/api/v1/projects/{pid}/comments",
                      headers=headers, params={"anchor": "tab:sales"}).json()
    assert [r["body"] for r in rows] == ["К сбыту"]


# --- Упоминания ---

def test_mentions_are_matched_case_insensitively():
    members = {"ivan@company.ru": "Ivan@Company.ru"}
    parsed = parse_mentions("привет @IVAN@Company.RU, посмотри", members)
    assert parsed.known == ["Ivan@Company.ru"] and parsed.unknown == []


def test_a_name_without_a_domain_is_not_a_mention():
    """`@ivan` — не адрес, и угадывать, кого имели в виду, платформа не станет:
    в организации бывают тёзки."""
    parsed = parse_mentions("@ivan посмотри", {"ivan@company.ru": "ivan@company.ru"})
    assert parsed.known == [] and parsed.unknown == []


def test_an_unknown_mention_is_named_not_swallowed(client, register):
    """«Позвал, и никто не пришёл» — худший вид тишины."""
    headers = register()
    pid = _project(client, headers)
    body = _say(client, headers, pid, "@nobody@else.ru глянь").json()
    assert body["unknown_mentions"] == ["nobody@else.ru"]
    assert body["notified"] == []


def test_a_mention_calls_a_colleague_but_grants_nothing(client, register):
    """Упоминание зовёт посмотреть; доступ решает роль в организации."""
    owner = register()
    pid = _project(client, owner)
    invite = _member(client, owner)
    body = _say(client, owner, pid, "@k@e.ru проверь, пожалуйста").json()
    assert body["notified"] == ["k@e.ru"]

    # Позванный видит проект — потому что он участник, а не потому, что его позвали.
    colleague = _activate(client, invite)
    assert client.get(f"/api/v1/projects/{pid}", headers=colleague).status_code == 200


def test_the_author_is_not_notified_about_their_own_words(client, register):
    """Письмо самому себе о собственной реплике — шум, из-за которого перестают читать
    остальные."""
    headers = register()
    pid = _project(client, headers)
    body = _say(client, headers, pid, "@owner@e.ru напоминание себе").json()
    assert body["notified"] == []


def test_a_mention_letter_goes_out_when_mail_is_configured(client, register,
                                                           monkeypatch):
    monkeypatch.setenv("MAIL_BACKEND", "memory")
    monkeypatch.setenv("PUBLIC_URL", "https://finans.example")
    mail.clear_outbox()
    owner = register()
    pid = _project(client, owner)
    _member(client, owner)
    mail.clear_outbox()          # приглашение участника ушло письмом (D1) — это не наше

    body = _say(client, owner, pid, "@k@e.ru посмотри строку I5",
                anchor="line:income:I5", label="Себестоимость (I5)").json()
    assert body["mail"]["attempted"] is True
    (to, letter), = mail.outbox()
    assert to == "k@e.ru"
    # Текст реплики внутри письма: иначе оно заставляет открыть систему, чтобы узнать,
    # стоило ли её открывать.
    assert "посмотри строку I5" in letter.text and "Себестоимость (I5)" in letter.text
    # И письмо честно говорит, что упоминание не открывает доступ.
    assert "не открывает доступ" in letter.text
    mail.clear_outbox()


def test_without_mail_nothing_is_promised(client, register):
    owner = register()
    pid = _project(client, owner)
    _member(client, owner)
    body = _say(client, owner, pid, "@k@e.ru глянь").json()
    assert body["notified"] == ["k@e.ru"]
    # Позвали, но письма не будет — и ответ не делает вид, что оно ушло.
    assert body["mail"]["attempted"] is False


# --- Что нельзя ---

def test_the_text_cannot_be_edited(client, register):
    """Отредактированная реплика, на которую ответили, переписывает историю: спор
    становится непонятным, а согласие — приписанным."""
    from app.main import app
    paths = app.openapi()["paths"]
    editable = [p for p, ops in paths.items()
                if "comments/{comment_id}" in p and ("put" in ops or "patch" in ops)]
    assert editable == []


def test_a_deleted_comment_says_so_instead_of_vanishing(client, register):
    headers = register()
    pid = _project(client, headers)
    cid = _say(client, headers, pid, "Ошибся").json()["comment"]["id"]

    client.delete(f"/api/v1/comments/{cid}", headers=headers)
    rows = client.get(f"/api/v1/projects/{pid}/comments", headers=headers).json()
    # Пропавшая без следа строка читается как не сказанная никогда, а на неё уже
    # могли ответить.
    assert rows[0]["deleted"] is True
    assert rows[0]["body"] == "Реплика удалена автором."


def test_an_admin_deletion_does_not_pretend_to_be_the_authors(client, register):
    """«Удалена автором» под чужим решением приписало бы его человеку."""
    owner = register()
    pid = _project(client, owner)
    colleague = _activate(client, _member(client, owner))
    cid = _say(client, colleague, pid, "Лишнее").json()["comment"]["id"]

    client.delete(f"/api/v1/comments/{cid}", headers=owner)
    rows = client.get(f"/api/v1/projects/{pid}/comments", headers=owner).json()
    assert rows[0]["body"] == "Реплика удалена администратором организации."


def test_someone_elses_comment_is_not_deletable_by_a_plain_member(client, register):
    owner = register()
    pid = _project(client, owner)
    colleague = _activate(client, _member(client, owner))
    cid = _say(client, owner, pid, "Моя реплика").json()["comment"]["id"]

    r = client.delete(f"/api/v1/comments/{cid}", headers=colleague)
    assert r.status_code == 403 and "администратор" in r.json()["detail"]


def test_an_empty_comment_is_refused_with_words(client, register):
    headers = register()
    pid = _project(client, headers)
    r = _say(client, headers, pid, "   ")
    assert r.status_code == 422 and "Пустой комментарий" in r.json()["detail"]


def test_a_comment_cannot_be_written_into_someone_elses_project(client, register):
    """Иначе обсуждение стало бы способом писать в чужую организацию мимо её прав."""
    owner = register()
    pid = _project(client, owner)
    stranger = register(email="alien@e.ru", org="Чужая")
    assert _say(client, stranger, pid, "привет").status_code == 404


# --- Закрытие обсуждения ---

def test_a_thread_can_be_closed_and_says_who_closed_it(client, register):
    """«Вопрос снят» без имени снявшего — это не ответ, а тишина."""
    headers = register()
    pid = _project(client, headers)
    cid = _say(client, headers, pid, "Почему такой рост?").json()["comment"]["id"]

    body = client.post(f"/api/v1/comments/{cid}/resolve", headers=headers).json()
    assert body["resolved"] is True and body["resolved_by"] == "owner@e.ru"

    again = client.delete(f"/api/v1/comments/{cid}/resolve", headers=headers).json()
    assert again["resolved"] is False and again["resolved_by"] == ""


def test_a_viewer_can_join_the_discussion(client, register):
    """Обсуждение затевают ради того, кто смотрит и спрашивает: инвестора, руководителя,
    приглашённого эксперта."""
    owner = register()
    pid = _project(client, owner)
    viewer = _activate(client, _member(client, owner, role="viewer"))
    assert _say(client, viewer, pid, "А почему так?").status_code == 201


# --- Второй продукт ---

def test_a_case_has_the_same_discussion(client, register):
    """У проекта и у дела обсуждение устроено одинаково — вторая копия правил разошлась
    бы с первой."""
    headers = register()
    sid = _case(client, headers)
    r = client.post(f"/api/v1/audit/subjects/{sid}/comments",
                    json={"body": "Сверить дебиторку", "anchor": "tab:flags",
                          "anchor_label": "Реестр флагов"}, headers=headers)
    assert r.status_code == 201

    rows = client.get(f"/api/v1/audit/subjects/{sid}/comments", headers=headers).json()
    assert rows[0]["subject_type"] == "case" and rows[0]["anchor"] == "tab:flags"


def test_discussions_of_a_project_and_a_case_do_not_mix(client, register):
    headers = register()
    pid = _project(client, headers)
    sid = _case(client, headers)
    _say(client, headers, pid, "К проекту")
    client.post(f"/api/v1/audit/subjects/{sid}/comments",
                json={"body": "К делу"}, headers=headers)

    assert [r["body"] for r in
            client.get(f"/api/v1/projects/{pid}/comments", headers=headers).json()
            ] == ["К проекту"]
    assert [r["body"] for r in
            client.get(f"/api/v1/audit/subjects/{sid}/comments",
                       headers=headers).json()] == ["К делу"]


# --- Режим чтения и выгрузки (B2) ---

def test_an_unpaid_organization_cannot_write_but_can_read(client, register, db_session):
    """Реплика — тоже содержимое организации: она хранится и переживает автора.
    Читать обсуждение неоплата не мешает — как и всё остальное чтение."""
    headers = register()
    pid = _project(client, headers)
    _say(client, headers, pid, "До неоплаты")
    crud.set_plan(db_session, _org_id(client, headers), "pro", status="past_due")

    assert _say(client, headers, pid, "После").status_code == 403
    assert client.get(f"/api/v1/projects/{pid}/comments",
                      headers=headers).status_code == 200
