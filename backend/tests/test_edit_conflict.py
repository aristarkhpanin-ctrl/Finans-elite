"""Защита от одновременной правки проекта и дела (пакет G, G2).

``PUT`` перезаписывает модель целиком. Двое открыли, оба сохранили — правки первого
исчезали молча. Проверяется не «вернулся 409», а обещания целиком:

* устаревшая правка **не записана**, а отказ называет, **кто и когда** сохранил раньше;
* ложных конфликтов нет: круг «прочитал → отослал назад» свой собственный, финализация
  коллегой (она двигает ``updated_at``, но не модель) и расчёт правкой не считаются;
* совпадение содержимого конфликтом не считается — терять нечего;
* без присланной ревизии поведение прежнее (ключи и скрипты, написанные до G2).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import apikeys, edit_conflict
from app.timefmt import when_utc

WRITE = sorted(p.value for p in apikeys.WRITE_PERMS)


@pytest.fixture
def team(client, register):
    """Владелец и аналитик одной организации — двое, кто правит одну модель."""
    owner = register("owner@e.ru", "Личная")
    org_id = client.post("/api/v1/organizations", json={"name": "Команда"},
                         headers=owner).json()["id"]
    owner_h = {**owner, "X-Organization-Id": org_id}
    analyst = register("analyst@e.ru", "Личная аналитика")
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": "analyst@e.ru", "role": "analyst"}, headers=owner_h)
    return SimpleNamespace(org_id=org_id, owner=owner_h,
                           analyst={**analyst, "X-Organization-Id": org_id})


def _project(client, headers) -> str:
    # Имя проекта и имя в заголовке модели совпадают — так создаёт проект интерфейс.
    # Разойдись они, «сохранение того же самого» на деле переименовывало бы проект.
    model = client.get("/api/v1/sample").json()
    model["header"] = {**model["header"], "name": "План"}
    return client.post("/api/v1/projects", json={"name": "План", "model": model},
                       headers=headers).json()["id"]


def _get(client, pid, headers) -> dict:
    return client.get(f"/api/v1/projects/{pid}", headers=headers).json()


def _save(client, pid, headers, loaded: dict, *, name: str | None = None,
          revision: str | None = "use-loaded"):
    """Сохранить модель, как это делает редактор: с ревизией той версии, что открыта."""
    model = dict(loaded["model"])
    if name is not None:
        model["header"] = {**model["header"], "name": name}
    body = {"name": model["header"]["name"], "model": model}
    if revision == "use-loaded":
        body["expected_revision"] = loaded["revision"]
    elif revision is not None:
        body["expected_revision"] = revision
    return client.put(f"/api/v1/projects/{pid}", json=body, headers=headers)


# --- Ревизия и её круг ---

def test_revision_is_in_the_answer(client, team):
    pid = _project(client, team.owner)
    assert len(_get(client, pid, team.owner)["revision"]) == 64      # sha256


def test_own_round_trip_is_not_a_conflict(client, team):
    """Прочитал → отослал назад → отослал ещё раз ответ сервера. Ни разу не 409.

    Сервер хранит не присланный JSON, а его нормализованный вид; ревизия ответа
    считается по сохранённому, иначе второе сохранение подряд спорило бы само с собой.
    """
    pid = _project(client, team.owner)
    first = _save(client, pid, team.owner, _get(client, pid, team.owner), name="Правка 1")
    assert first.status_code == 200
    second = _save(client, pid, team.owner, first.json(), name="Правка 2")
    assert second.status_code == 200
    assert second.json()["revision"] != first.json()["revision"]


# --- Конфликт ---

def test_a_stale_save_is_refused_and_names_who_saved(client, team):
    pid = _project(client, team.owner)
    owner_view = _get(client, pid, team.owner)
    analyst_view = _get(client, pid, team.analyst)

    assert _save(client, pid, team.analyst, analyst_view, name="Версия аналитика").status_code == 200
    r = _save(client, pid, team.owner, owner_view, name="Версия владельца")

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "Проект изменён" in detail and "он сохранён" in detail
    assert "analyst@e.ru" in detail and "UTC" in detail
    assert "Ваши правки не записаны" in detail
    # Главное обещание: правка аналитика не стёрта.
    assert _get(client, pid, team.owner)["name"] == "Версия аналитика"


def test_finalization_by_a_colleague_is_not_a_conflict(client, team):
    """Финализация пишет в строку статус и снимок ревью и двигает ``updated_at`` — модель
    при этом прежняя. Версия по ``updated_at`` отвечала бы здесь «кто-то сохранил».
    """
    pid = _project(client, team.owner)
    owner_view = _get(client, pid, team.owner)

    r = client.post(f"/api/v1/projects/{pid}/finalize", json={"acknowledge": True},
                    headers=team.analyst)
    assert r.status_code == 200
    after = _get(client, pid, team.owner)
    assert after["updated_at"] != owner_view["updated_at"]     # ловушка на месте…
    assert after["revision"] == owner_view["revision"]         # …а ревизия прежняя

    assert _save(client, pid, team.owner, owner_view, name="Правка после").status_code == 200


def test_calculation_does_not_move_the_revision(client, team):
    pid = _project(client, team.owner)
    before = _get(client, pid, team.owner)
    assert client.post(f"/api/v1/projects/{pid}/calculate",
                       headers=team.analyst).status_code == 200
    assert _get(client, pid, team.owner)["revision"] == before["revision"]


def test_identical_content_is_not_a_conflict(client, team):
    """Коллега сохранил ровно то же самое — терять нечего, и отказ был бы пустым."""
    pid = _project(client, team.owner)
    owner_view = _get(client, pid, team.owner)
    assert _save(client, pid, team.analyst, _get(client, pid, team.analyst)).status_code == 200
    assert _save(client, pid, team.owner, owner_view, name="Моя правка").status_code == 200


def test_a_restored_version_is_named_as_such(client, team):
    pid = _project(client, team.owner)
    vid = client.post(f"/api/v1/projects/{pid}/versions", json={"label": "до правок"},
                      headers=team.analyst).json()["id"]
    _save(client, pid, team.analyst, _get(client, pid, team.analyst), name="Правка")
    owner_view = _get(client, pid, team.owner)               # открыл уже с правкой

    assert client.post(f"/api/v1/projects/{pid}/versions/{vid}/restore",
                       headers=team.analyst).status_code == 200
    r = _save(client, pid, team.owner, owner_view, name="Поверх")

    assert r.status_code == 409
    assert "восстановлена версия" in r.json()["detail"]


def test_a_write_through_an_api_key_names_the_key(client, team):
    """Запись по ключу подписана в журнале автором ключа **и** ключом — отказ называет оба."""
    body = client.post(f"/api/v1/organizations/{team.org_id}/api-keys",
                       json={"name": "Обмен с 1С", "scopes": WRITE},
                       headers=team.owner).json()
    key = {"Authorization": f"Bearer {body['token']}"}
    pid = _project(client, team.owner)
    analyst_view = _get(client, pid, team.analyst)

    assert _save(client, pid, key, _get(client, pid, key), name="Из 1С").status_code == 200
    r = _save(client, pid, team.analyst, analyst_view, name="Руками")

    assert r.status_code == 409
    assert "через ключ API «Обмен с 1С" in r.json()["detail"]
    assert "owner@e.ru" in r.json()["detail"]


def test_without_a_revision_the_old_overwrite_stays(client, team):
    """Ключи и скрипты, написанные до G2, версию не присылают — и не должны сломаться."""
    pid = _project(client, team.owner)
    owner_view = _get(client, pid, team.owner)
    _save(client, pid, team.analyst, _get(client, pid, team.analyst), name="Правка")
    assert _save(client, pid, team.owner, owner_view, name="Поверх",
                 revision=None).status_code == 200


# --- Дело «Аудита» ---

def _case(client, headers) -> str:
    return client.post("/api/v1/audit/subjects",
                       json={"name": "Дело", "model": {"name": "Дело", "periods": [],
                                                       "lines": []}},
                       headers=headers).json()["id"]


def test_a_case_has_the_same_protection_and_its_own_grammar(client, team):
    """У дела средний род: «дело изменено, оно сохранено». Одна формулировка на оба
    продукта давала бы ошибку в каждом втором отказе."""
    cid = _case(client, team.owner)
    owner_view = client.get(f"/api/v1/audit/subjects/{cid}", headers=team.owner).json()
    analyst_view = client.get(f"/api/v1/audit/subjects/{cid}", headers=team.analyst).json()

    def save(headers, view, name):
        return client.put(f"/api/v1/audit/subjects/{cid}",
                          json={"name": name, "model": view["model"],
                                "expected_revision": view["revision"]},
                          headers=headers)

    assert save(team.analyst, analyst_view, "Дело (аналитик)").status_code == 200
    r = save(team.owner, owner_view, "Дело (владелец)")

    assert r.status_code == 409
    assert "Дело изменено" in r.json()["detail"] and "оно сохранено" in r.json()["detail"]
    assert client.get(f"/api/v1/audit/subjects/{cid}",
                      headers=team.owner).json()["name"] == "Дело (аналитик)"


# --- Слова отказа ---

def test_without_a_journal_entry_the_refusal_says_so(client, team, db_session):
    """Кто изменил, журнал знает не всегда — и отказ не выдумывает автора."""
    pid = _project(client, team.owner)
    text = edit_conflict.conflict_message(db_session, team.org_id, "project", pid + "-нет")
    assert "журнал не называет" in text


def test_time_is_named_in_utc_even_when_the_database_forgot_the_zone():
    """SQLite отдаёт время без пояса; ``astimezone`` приняло бы его за местное."""
    naive = datetime(2026, 9, 5, 14, 5)
    moscow = datetime(2026, 9, 5, 17, 5, tzinfo=timezone(timedelta(hours=3)))
    assert when_utc(naive) == "05.09.2026 14:05 UTC"
    assert when_utc(moscow) == "05.09.2026 14:05 UTC"
