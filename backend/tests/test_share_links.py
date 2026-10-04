"""Ссылка для инвестора или банка (пакет L, L4).

Ссылка открывает **снимок** проекта без входа, и главное, что держит этот файл: копия не
меняется от правки проекта; ссылка не живёт дольше срока и гаснет сразу при закрытии;
отказы называют свою причину разными словами; каждое открытие видно отправителю в
журнале — и никто, кроме предъявителя секрета, ссылку не откроет.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO

import pytest
from docx import Document

from app import share_links
from app.db_models import AuditLogEntry, ShareLink
from app.share_links import MAX_DAYS, OPEN


@pytest.fixture
def owner(client, register):
    headers = register("owner@share.test", "Орг")
    model = client.get("/api/v1/sample").json()
    pid = client.post("/api/v1/projects", headers=headers,
                      json={"name": "Завод", "model": model}).json()["id"]
    return headers, pid, model


def _share(client, owner, **body):
    headers, pid, _ = owner
    r = client.post(f"/api/v1/projects/{pid}/share-links", headers=headers,
                    json={"label": "Сбербанк, кредитный комитет", **body})
    assert r.status_code == 201, r.text
    return r.json()


def test_a_link_opens_the_snapshot_without_login(client, owner):
    _, _, model = owner
    link = _share(client, owner)
    assert link["path"] == f"/s/{link['token']}" and link["state"] == "active"
    assert link["version_label"].startswith("Отправлено: Сбербанк")
    assert any("показывается один раз" in n for n in link["notes"])
    r = client.get(f"/api/v1/shared/{link['token']}")          # без заголовков входа
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project_name"] == "Завод" and body["shared_for"] == "Сбербанк, кредитный комитет"
    assert body["result"]["n"] > 0
    assert body["discount_rate_annual"] == str(Decimal(model["settings"]["discount_rate_annual"]))
    assert any("копия плана на момент отправки" in n for n in body["notes"])
    assert any("не известно" in n for n in body["notes"])


def test_the_copy_does_not_follow_later_edits(client, owner):
    """Показывают то, что отправили: правка проекта после отправки копию не меняет."""
    headers, pid, model = owner
    link = _share(client, owner)
    before = client.get(f"/api/v1/shared/{link['token']}").json()["result"]["metrics"]["npv"]
    edited = dict(model)
    edited["financing"] = {**model["financing"], "loans": []}
    assert client.put(f"/api/v1/projects/{pid}", headers=headers,
                      json={"model": edited}).status_code == 200
    after = client.get(f"/api/v1/shared/{link['token']}").json()["result"]["metrics"]["npv"]
    assert after == before


def test_every_opening_is_in_the_senders_journal(client, owner, db_session):
    headers, pid, _ = owner
    link = _share(client, owner)
    client.get(f"/api/v1/shared/{link['token']}")
    client.get(f"/api/v1/shared/{link['token']}/business-plan.docx")
    rows = db_session.query(AuditLogEntry).filter(AuditLogEntry.action == OPEN).all()
    assert [r.details for r in rows] == ["просмотр", "бизнес-план (DOCX)"]
    assert rows[0].actor_email == "по ссылке «Сбербанк, кредитный комитет»"
    listed = client.get(f"/api/v1/projects/{pid}/share-links", headers=headers).json()
    assert listed["links"][0]["opens"] == 2 and listed["links"][0]["last_opened_at"] is not None
    assert any("не известно" in n for n in listed["notes"])


def test_the_document_says_whom_the_copy_is_for(client, owner):
    link = _share(client, owner)
    r = client.get(f"/api/v1/shared/{link['token']}/business-plan.docx")
    assert r.status_code == 200
    text = "\n".join(p.text for p in Document(BytesIO(r.content)).paragraphs)
    assert "Копия для: Сбербанк, кредитный комитет. Открыта по ссылке до" in text


def test_refusals_have_their_own_words(client, owner, db_session):
    headers, pid, _ = owner
    assert client.get("/api/v1/shared/fs_nope").status_code == 404
    assert client.get("/api/v1/shared/not-a-token").json()["detail"].startswith(
        "Ссылка не найдена")

    revoked = _share(client, owner)
    assert client.delete(f"/api/v1/projects/{pid}/share-links/{revoked['id']}",
                         headers=headers).status_code == 204
    r = client.get(f"/api/v1/shared/{revoked['token']}")
    assert r.status_code == 410 and "закрыл отправитель" in r.json()["detail"]

    expired = _share(client, owner)
    row = db_session.get(ShareLink, expired["id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    r = client.get(f"/api/v1/shared/{expired['token']}")
    assert r.status_code == 410 and "Срок ссылки истёк" in r.json()["detail"]


def test_a_deleted_version_kills_the_link_with_a_reason(client, owner):
    headers, pid, _ = owner
    link = _share(client, owner)
    assert client.delete(f"/api/v1/projects/{pid}/versions/{link['version_id']}",
                         headers=headers).status_code == 204
    r = client.get(f"/api/v1/shared/{link['token']}")
    assert r.status_code in (404, 410)


def test_the_term_is_capped_and_the_cap_is_named(client, owner):
    link = _share(client, owner, days=720)
    left = datetime.fromisoformat(link["expires_at"]).replace(tzinfo=timezone.utc) \
        - datetime.now(timezone.utc)
    assert timedelta(days=MAX_DAYS - 1) < left <= timedelta(days=MAX_DAYS)
    assert any(f"на {MAX_DAYS} дней вместо 720" in n for n in link["notes"])


def test_only_a_fingerprint_is_stored(client, owner, db_session):
    link = _share(client, owner)
    row = db_session.get(ShareLink, link["id"])
    assert row.fingerprint == share_links.fingerprint(link["token"])
    assert link["token"] not in (row.fingerprint, row.label, row.created_by)
    # Список ссылок секрета не повторяет.
    headers, pid, _ = owner
    listed = client.get(f"/api/v1/projects/{pid}/share-links", headers=headers).json()
    assert "token" not in listed["links"][0]


def test_a_label_is_required_and_viewers_cannot_share(client, owner, register):
    headers, pid, _ = owner
    r = client.post(f"/api/v1/projects/{pid}/share-links", headers=headers, json={"label": " "})
    assert r.status_code == 422 and "для кого" in r.json()["detail"]
    stranger = register("other@share.test", "Чужая")
    assert client.post(f"/api/v1/projects/{pid}/share-links", headers=stranger,
                       json={"label": "x"}).status_code == 404


def test_an_existing_version_can_be_shared(client, owner):
    headers, pid, _ = owner
    version = client.post(f"/api/v1/projects/{pid}/versions", headers=headers,
                          json={"label": "План для комитета"}).json()
    link = _share(client, owner, version_id=version["id"])
    assert link["version_label"] == "План для комитета"


def test_the_organization_purge_takes_the_links(client, owner, db_session):
    """Организация ушла (F6) — её ссылки не продолжают открывать её числа."""
    link = _share(client, owner)
    headers, _, _ = owner
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    r = client.request("DELETE", f"/api/v1/organizations/{org_id}", headers=headers,
                       json={"password": "secret123"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/v1/shared/{link['token']}").status_code == 404


def test_the_organization_export_lists_links_without_their_secret(client, owner):
    """Выгрузка организации (F6) — всё, что платформа о ней хранит; секрета ссылки она
    не хранит, и файл не должен выглядеть местом, где он нашёлся."""
    link = _share(client, owner)
    headers, _, _ = owner
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    r = client.get(f"/api/v1/organizations/{org_id}/export", headers=headers)
    assert r.status_code == 200
    assert link["token"] not in r.text
    shared = r.json()["ссылки_для_просмотра"]
    assert shared[0]["для_кого"] == "Сбербанк, кредитный комитет"
    assert shared[0]["проект"] == "Завод"


def test_an_unpaid_organization_cannot_open_a_link_but_can_close_one(client, owner,
                                                                    db_session):
    """Режим чтения при неоплате (B2): открыть ссылку — правка (снимок версии), и она
    закрыта; закрыть дверь наружу — действие безопасности, и оно открыто всегда."""
    from app import crud

    headers, pid, _ = owner
    link = _share(client, owner)
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    crud.set_plan(db_session, org_id, "free", status="past_due", product="business")

    r = client.post(f"/api/v1/projects/{pid}/share-links", headers=headers,
                    json={"label": "Ещё один банк"})
    assert r.status_code == 403
    assert client.delete(f"/api/v1/projects/{pid}/share-links/{link['id']}",
                         headers=headers).status_code == 204
    assert client.get(f"/api/v1/shared/{link['token']}").status_code == 410


def test_the_secret_does_not_reach_the_access_log(client, owner):
    """Секрет стоит прямо в адресе: лог доступа, отдающий путь как есть, раздавал бы
    живые ссылки всем, кто читает логи (найдено сквозным тестом L4)."""
    import logging

    from app.error_tracking import redact

    link = _share(client, owner)
    lines: list[str] = []

    class Grab(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(record.getMessage())

    grab = Grab()
    logging.getLogger("finans").addHandler(grab)
    try:
        assert client.get(f"/api/v1/shared/{link['token']}").status_code == 200
    finally:
        logging.getLogger("finans").removeHandler(grab)
    shared = [line for line in lines if "/api/v1/shared/" in line]
    assert shared and all(link["token"] not in line for line in shared)
    assert "fs_[ссылка скрыта]" in shared[0]
    # Та же вычистка — у отчёта об ошибке страницы с секретом в адресе (G7).
    assert link["token"] not in redact(f"https://app/s/{link['token']}")
