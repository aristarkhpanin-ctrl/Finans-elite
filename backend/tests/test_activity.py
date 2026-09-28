"""Активность организации (NEXT-STEPS.md, E1).

Сводка собрана из того, что платформа уже знает, и обязана **не обещать лишнего**:
пустая отметка присутствия — «неизвестно», ноль действий — «ничего не менял», даты
последнего расчёта — не «сколько раз считали».
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.activity import STALE, build_activity


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _project(client, headers, name="Проект") -> str:
    return client.post("/api/v1/projects",
                       json={"name": name, "model": client.get("/api/v1/sample").json()},
                       headers=headers).json()["id"]


def _case(client, headers, name="Дело") -> str:
    return client.post("/api/v1/audit/subjects",
                       json={"name": name,
                             "model": {"name": name, "periods": [], "lines": []}},
                       headers=headers).json()["id"]


# --- Что сводка показывает ---

def test_the_summary_shows_who_works_and_what_is_alive(client, register):
    headers = register()
    org = _org_id(client, headers)
    pid = _project(client, headers, "Живой")
    client.post(f"/api/v1/projects/{pid}/calculate", headers=headers)
    _case(client, headers, "Дело")

    body = client.get(f"/api/v1/organizations/{org}/activity", headers=headers).json()
    assert [m["email"] for m in body["members"]] == ["owner@e.ru"]
    kinds = {e["kind"] for e in body["entities"]}
    assert kinds == {"project", "case"}
    project = next(e for e in body["entities"] if e["kind"] == "project")
    assert project["last_calculated_at"] is not None
    # Дела не считаются тем же способом: у них даты расчёта нет вовсе, и подставлять
    # сюда что-то другое значило бы выдумать число.
    case = next(e for e in body["entities"] if e["kind"] == "case")
    assert case["last_calculated_at"] is None


def test_actions_are_counted_from_the_journal(client, register):
    """«Действий» — это записи журнала, а не запросы: чтение он не пишет."""
    headers = register()
    org = _org_id(client, headers)
    before = client.get(f"/api/v1/organizations/{org}/activity",
                        headers=headers).json()["members"][0]["actions"]
    _project(client, headers)
    _project(client, headers, "Второй")
    # Просмотры — не действия: список проектов журнал не пишет.
    for _ in range(5):
        client.get("/api/v1/projects", headers=headers)

    after = client.get(f"/api/v1/organizations/{org}/activity",
                       headers=headers).json()["members"][0]["actions"]
    assert after == before + 2


def test_open_discussions_are_shown_next_to_the_entity(client, register):
    headers = register()
    org = _org_id(client, headers)
    pid = _project(client, headers)
    client.post(f"/api/v1/projects/{pid}/comments", json={"body": "Вопрос"},
                headers=headers)

    entity = next(e for e in client.get(f"/api/v1/organizations/{org}/activity",
                                        headers=headers).json()["entities"]
                  if e["id"] == pid)
    assert entity["open_comments"] == 1


def test_a_sleeping_entity_is_marked(client, register, db_session):
    """Проект, который не открывали квартал, обычно закончен или заброшен — и то и
    другое повод про него вспомнить."""
    headers = register()
    org = _org_id(client, headers)
    pid = _project(client, headers, "Заброшенный")

    from app.db_models import Project
    project = db_session.get(Project, pid)
    project.updated_at = datetime.now(timezone.utc) - STALE - timedelta(days=1)
    db_session.commit()

    entity = next(e for e in client.get(f"/api/v1/organizations/{org}/activity",
                                        headers=headers).json()["entities"]
                  if e["id"] == pid)
    assert entity["stale"] is True


# --- Чего сводка не обещает ---

def test_an_unknown_presence_is_not_a_never(client, register, db_session):
    """Пустая отметка — «неизвестно»: она ведётся не с первого дня платформы."""
    headers = register()
    org = _org_id(client, headers)
    client.post(f"/api/v1/organizations/{org}/members",
                json={"email": "k@e.ru", "full_name": "Коллега", "role": "editor"},
                headers=headers)

    body = client.get(f"/api/v1/organizations/{org}/activity", headers=headers).json()
    invited = next(m for m in body["members"] if m["email"] == "k@e.ru")
    assert invited["last_seen_at"] is None
    assert any("неизвестно" in n for n in body["notes"])


def test_the_summary_says_what_it_does_not_know(client, register):
    """Без границ сводка читается как отчёт о людях: «действий 0» превращается в
    «бездельничает», а «не считали» — в «не заходил»."""
    headers = register()
    org = _org_id(client, headers)
    notes = client.get(f"/api/v1/organizations/{org}/activity",
                       headers=headers).json()["notes"]
    assert any("Просмотры журнал не пишет" in n for n in notes)
    assert any("Расчётов платформа не считает" in n for n in notes)


def test_the_window_is_named_not_implied(client, register):
    """«Действий 12» без окна — это «за всё время» или «за месяц»? Окно названо числом."""
    headers = register()
    org = _org_id(client, headers)
    body = client.get(f"/api/v1/organizations/{org}/activity", headers=headers).json()
    assert body["window_days"] == 30 and body["stale_days"] == 90


def test_old_actions_fall_out_of_the_window(client, register, db_session):
    headers = register()
    org = _org_id(client, headers)
    _project(client, headers)

    from app.db_models import AuditLogEntry
    for entry in db_session.query(AuditLogEntry).all():
        entry.created_at = datetime.now(timezone.utc) - timedelta(days=60)
    db_session.commit()

    body = client.get(f"/api/v1/organizations/{org}/activity", headers=headers).json()
    assert body["members"][0]["actions"] == 0


# --- Границы доступа ---

def test_the_summary_is_for_those_who_answer_for_the_organization(client, register):
    """Тот же довод, что у журнала: сводка отвечает на вопрос об **остальных**."""
    owner = register()
    org = _org_id(client, owner)
    invite = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "k@e.ru", "full_name": "К", "role": "editor"},
                         headers=owner).json()
    token = client.post("/api/v1/auth/activate",
                        json={"token": invite["invite_token"],
                              "password": "kollega-parol7"}).json()["access_token"]
    editor = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/v1/organizations/{org}/activity",
                      headers=editor).status_code == 403


def test_the_summary_stays_inside_its_organization(client, register, db_session):
    first = register()
    _project(client, first, "Мой")
    second = register(email="alien@e.ru", org="Чужая")
    _project(client, second, "Чужой")

    org = _org_id(client, first)
    names = {e["name"] for e in
             client.get(f"/api/v1/organizations/{org}/activity",
                        headers=first).json()["entities"]}
    assert names == {"Мой"}


def test_the_report_is_a_reader_and_changes_nothing(client, register, db_session):
    """Сводка ничего не пересчитывает и не отмечает: экран наблюдения, который меняет
    наблюдаемое, показывает себя, а не работу."""
    headers = register()
    org = _org_id(client, headers)
    _project(client, headers)

    from app.db_models import AuditLogEntry
    before = db_session.query(AuditLogEntry).count()
    build_activity(db_session, org)
    assert db_session.query(AuditLogEntry).count() == before
