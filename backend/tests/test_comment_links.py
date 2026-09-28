"""Ссылки на материалы в обсуждении (OPEN-DECISIONS §6).

Разговор о числах упирается в «вот выписка», а файлового хранилища у платформы нет и
пока не будет: три вопроса, на которые надо ответить до него, перечислены в памятке.
Поэтому реплика несёт **адрес**, а не файл — и платформа говорит это рядом.

Проверяется обещание, а не разметка: платформа файл не хранит и по ссылке **не ходит**,
ссылка выводится из текста (а значит, уходит с ним при удалении), ссылкой считается
только http(s), а то, что ей не стало, **названо** автору.
"""
from __future__ import annotations

from app import mail
from app.comments import LINKS_NOTE, MAX_LINKS, parse_links

DR = "https://dataroom.example/deal/вложение.pdf"


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _project(client, headers, name="Проект") -> str:
    model = client.get("/api/v1/sample").json()
    return client.post("/api/v1/projects", json={"name": name, "model": model},
                       headers=headers).json()["id"]


def _say(client, headers, pid, text):
    return client.post(f"/api/v1/projects/{pid}/comments", json={"body": text},
                       headers=headers)


def _rows(client, headers, pid) -> list[dict]:
    return client.get(f"/api/v1/projects/{pid}/comments", headers=headers).json()


# --- Что считается ссылкой ---

def test_an_address_in_the_text_becomes_a_link():
    assert parse_links(f"смотри {DR}").known == [DR]


def test_trailing_punctuation_is_not_part_of_the_address():
    """«смотри …/a.pdf.» — это адрес и точка, а не адрес с точкой."""
    assert parse_links(f"смотри {DR}.").known == [DR]
    assert parse_links(f"({DR})").known == [DR]


def test_only_http_is_a_link_and_the_rest_is_named():
    """Молчание тут хуже отказа: автор будет думать, что приложил выписку, а коллега
    не найдёт ничего."""
    links = parse_links("вот ftp://server/x.xlsx и \\\\сервер\\папка\\отчёт.xlsx")
    assert links.known == []
    assert links.unsupported == ["ftp://server/x.xlsx", "\\\\сервер\\папка\\отчёт.xlsx"]


def test_a_dangerous_scheme_never_becomes_clickable():
    """`javascript:` в разметке — это дыра, а не вложение: такой текст ссылкой не
    становится вовсе."""
    links = parse_links("javascript:alert(1) и data:text/html;base64,AAA")
    assert links.known == []


def test_only_the_scheme_is_lowercased():
    """Путь на чужом сервере вправе различать регистр: `/Отчёт.pdf` — не `/отчёт.pdf`."""
    assert parse_links("HTTPS://a.ru/Отчёт.pdf").known == ["https://a.ru/Отчёт.pdf"]


def test_the_same_address_twice_is_one_link():
    assert parse_links(f"{DR} и снова {DR}").known == [DR]


# --- Через продукт ---

def test_the_reply_carries_the_link_and_the_caveat(client, register):
    headers = register()
    pid = _project(client, headers)
    body = _say(client, headers, pid, f"Выписка тут: {DR}").json()

    assert body["comment"]["links"] == [DR]
    # Оговорка едет **вместе со ссылкой**, а не лежит в документации.
    assert body["comment"]["links_note"] == LINKS_NOTE
    assert "не хранит" in body["comment"]["links_note"]
    assert "по ним не ходит" in body["comment"]["links_note"]


def test_a_reply_without_links_carries_no_caveat(client, register):
    """Оговорка, стоящая везде, перестаёт читаться."""
    headers = register()
    pid = _project(client, headers)
    body = _say(client, headers, pid, "Просто вопрос").json()
    assert body["comment"]["links"] == [] and body["comment"]["links_note"] == ""


def test_what_did_not_become_a_link_is_named_to_the_author(client, register):
    headers = register()
    pid = _project(client, headers)
    body = _say(client, headers, pid, "файл тут: \\\\сервер\\общая\\выписка.xlsx").json()
    assert body["comment"]["unsupported_links"] == ["\\\\сервер\\общая\\выписка.xlsx"]
    assert body["comment"]["links"] == []


def test_a_deleted_reply_takes_its_links_with_it(client, register, db_session):
    """«Надгробие» обязано унести адрес комнаты данных с собой.

    Держится это на том, что **чистить нечего**: удаление стирает текст, а ссылки из
    него выводятся. Отдельное поле со ссылками было бы вторым местом, которое надо
    чистить, — и однажды его забыли бы. Поэтому тест смотрит и в базу тоже: пустой
    ответ при сохранённом адресе означал бы, что адрес всё ещё лежит у нас.
    """
    headers = register()
    pid = _project(client, headers)
    cid = _say(client, headers, pid, f"Выписка: {DR}").json()["comment"]["id"]
    client.delete(f"/api/v1/comments/{cid}", headers=headers)

    row = _rows(client, headers, pid)[0]
    assert row["deleted"] is True
    assert row["links"] == [] and row["links_note"] == ""
    assert DR not in row["body"]

    # И в самой базе адреса не осталось: ответ без ссылки поверх сохранённого адреса
    # был бы отчётом об удалении, а не удалением.
    from app.db_models import Comment
    stored = db_session.query(Comment).filter(Comment.id == cid).one()
    assert DR not in stored.body


def test_too_many_links_are_refused_with_the_reason(client, register):
    headers = register()
    pid = _project(client, headers)
    text = " ".join(f"https://dr.example/{i}.pdf" for i in range(MAX_LINKS + 1))
    r = _say(client, headers, pid, text)
    assert r.status_code == 422 and "опись" in r.json()["detail"]


def test_exactly_the_limit_still_goes_through(client, register):
    headers = register()
    pid = _project(client, headers)
    text = " ".join(f"https://dr.example/{i}.pdf" for i in range(MAX_LINKS))
    r = _say(client, headers, pid, text)
    assert r.status_code == 201 and len(r.json()["comment"]["links"]) == MAX_LINKS


# --- Платформа по ссылке не ходит ---

def test_the_platform_never_fetches_the_address(client, register, monkeypatch):
    """Ходить по ссылке нельзя по трём причинам сразу: адрес комнаты данных утёк бы в
    наши логи, внутренний адрес превратил бы платформу в чужой сканер, а одноразовую
    ссылку наш запрос просто сжёг бы — и коллега открыл бы пустоту."""
    import urllib.request

    def refuse(*a, **k):                       # pragma: no cover — не должно вызываться
        raise AssertionError("платформа пошла по ссылке из реплики")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    headers = register()
    pid = _project(client, headers)
    assert _say(client, headers, pid,
                "http://127.0.0.1:1/secret").status_code == 201


def test_the_letter_repeats_the_caveat_where_the_link_is_clicked(client, register,
                                                                 monkeypatch, db_session):
    """Письмо — то место, где по ссылке и щёлкнут: экран получатель может не открыть."""
    from app import crud

    monkeypatch.setenv("MAIL_BACKEND", "memory")
    monkeypatch.setenv("PUBLIC_URL", "https://finans.example")
    mail.clear_outbox()
    owner = register()
    pid = _project(client, owner)
    org = _org_id(client, owner)
    client.post(f"/api/v1/organizations/{org}/members",
                json={"email": "k@e.ru", "full_name": "К", "role": "editor"},
                headers=owner)
    crud.mark_email_verified(db_session, crud.get_user_by_email(db_session, "k@e.ru"))
    mail.clear_outbox()

    _say(client, owner, pid, f"@k@e.ru выписка тут: {DR}")
    (_, letter), = mail.outbox()
    assert DR in letter.text and "Файлов платформа не хранит" in letter.text


def test_a_letter_without_links_does_not_carry_the_caveat(client, register, monkeypatch,
                                                           db_session):
    from app import crud

    monkeypatch.setenv("MAIL_BACKEND", "memory")
    monkeypatch.setenv("PUBLIC_URL", "https://finans.example")
    mail.clear_outbox()
    owner = register()
    pid = _project(client, owner)
    org = _org_id(client, owner)
    client.post(f"/api/v1/organizations/{org}/members",
                json={"email": "k@e.ru", "full_name": "К", "role": "editor"},
                headers=owner)
    crud.mark_email_verified(db_session, crud.get_user_by_email(db_session, "k@e.ru"))
    mail.clear_outbox()

    _say(client, owner, pid, "@k@e.ru посмотри строку I5")
    (_, letter), = mail.outbox()
    assert "Файлов платформа не хранит" not in letter.text


# --- Хранилища нет, и это решение ---

def test_the_platform_stores_no_files_at_all():
    """Перечень-тест против тихого появления хранилища: пока на три вопроса памятки
    (где байты, кто платит, что при удалении) нет ответа, маршрута загрузки быть не
    должно. Первый же `POST .../files` здесь и остановится."""
    from app.main import app

    uploads = [path for path in app.openapi()["paths"]
               if "upload" in path or path.endswith("/files")]
    assert uploads == [], uploads
