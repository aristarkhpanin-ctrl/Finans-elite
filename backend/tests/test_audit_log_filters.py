"""Отбор, поиск и выгрузка журнала + события входа (ADMIN-DECOMPOSITION.md, фаза A2).

Журнал существовал, но пользоваться им было нельзя: эндпоинт умел только «последние N»,
а экран не передавал и этого. На двадцати тысячах записей такой журнал есть, а ответа
из него не достать — и при разборе инцидента он бесполезен ровно тогда, когда нужен.

Отдельно проверяется то, что легко сделать неправильно: счётчик обязан считать **под тем
же отбором**, что и список, а неудачный вход по несуществующему адресу не должен
оставлять следа — иначе журнал подсказывает, какие адреса у нас есть.
"""
from __future__ import annotations


def _org(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _log(client, headers, org, **params):
    return client.get(f"/api/v1/organizations/{org}/audit-log", params=params,
                      headers=headers).json()


def _seed(client, headers) -> str:
    """Несколько разных действий, чтобы было что отбирать."""
    org = _org(client, headers)
    client.post("/api/v1/projects", json={"name": "Завод", "model": {}}, headers=headers)
    client.post("/api/v1/projects", json={"name": "Склад", "model": {}}, headers=headers)
    client.post("/api/v1/audit/subjects/demo", headers=headers)
    client.post(f"/api/v1/organizations/{org}/members",
                json={"email": "к@e.ru", "full_name": "Коллега", "role": "editor"},
                headers=headers)
    return org


# --- первый продукт больше не молчит ---

def test_project_lifecycle_is_recorded(client, auth_headers):
    """В «Элит» не писалось ничего: ни создание, ни правка, ни выгрузка."""
    org = _org(client, auth_headers)
    pid = client.post("/api/v1/projects", json={"name": "Завод", "model": {}},
                      headers=auth_headers).json()["id"]
    client.put(f"/api/v1/projects/{pid}", json={"name": "Завод-2"}, headers=auth_headers)
    client.get(f"/api/v1/projects/{pid}/business-plan.docx", headers=auth_headers)
    client.post(f"/api/v1/projects/{pid}/versions", json={"label": "v1"}, headers=auth_headers)
    client.delete(f"/api/v1/projects/{pid}", headers=auth_headers)

    actions = [e["action"] for e in _log(client, auth_headers, org)["entries"]]
    for expected in ("project.create", "project.update", "project.export",
                     "project.version", "project.delete"):
        assert expected in actions, expected


def test_calculation_is_not_recorded(client, auth_headers):
    """Расчёт — просмотр результата: экран зовёт его при каждом открытии, и записи о
    нём утопили бы журнал (правило «журнал не пишет чтение»)."""
    org = _org(client, auth_headers)
    pid = client.post("/api/v1/projects", json={"name": "Завод", "model": {}},
                      headers=auth_headers).json()["id"]
    for _ in range(3):
        client.post(f"/api/v1/projects/{pid}/calculate", headers=auth_headers)
    actions = [e["action"] for e in _log(client, auth_headers, org)["entries"]]
    assert "project.calculate" not in actions


# --- отбор ---

def test_filter_by_action_and_the_counter_agrees_with_the_list(client, auth_headers):
    """«Показано 2 из 12» врало бы, считай счётчик весь журнал вместо отобранного."""
    org = _seed(client, auth_headers)
    page = _log(client, auth_headers, org, action="project.create")
    assert [e["action"] for e in page["entries"]] == ["project.create"] * 2
    assert page["total"] == 2

    whole = _log(client, auth_headers, org)
    assert whole["total"] > page["total"]


def test_filter_by_entity_type_and_actor(client, auth_headers):
    org = _seed(client, auth_headers)
    only_projects = _log(client, auth_headers, org, entity_type="project")
    assert {e["entity_type"] for e in only_projects["entries"]} == {"project"}

    mine = _log(client, auth_headers, org, actor="owner@e.ru")
    assert mine["total"] == _log(client, auth_headers, org)["total"]
    assert _log(client, auth_headers, org, actor="никто@e.ru")["total"] == 0


def test_search_looks_where_a_person_remembers(client, auth_headers):
    """Ищут по тому, что помнят: имя объекта, кто сделал, примечание."""
    org = _seed(client, auth_headers)
    assert _log(client, auth_headers, org, q="Склад")["total"] == 1
    assert _log(client, auth_headers, org, q="к@e.ru")["total"] >= 1      # по актору/объекту
    assert _log(client, auth_headers, org, q="демо-дело")["total"] == 1   # по примечанию
    assert _log(client, auth_headers, org, q="ничего такого")["total"] == 0


def test_date_range_filters(client, auth_headers):
    org = _seed(client, auth_headers)
    total = _log(client, auth_headers, org)["total"]
    assert _log(client, auth_headers, org, since="2000-01-01T00:00:00")["total"] == total
    assert _log(client, auth_headers, org, until="2000-01-01T00:00:00")["total"] == 0


def test_page_offers_only_what_actually_happened(client, auth_headers):
    """Фильтр предлагает встречавшееся, а не весь каталог кодов."""
    org = _seed(client, auth_headers)
    page = _log(client, auth_headers, org)
    assert "project.create" in page["actions"]
    assert "case.delete" not in page["actions"]        # такого в этой организации не было
    assert page["actors"] == ["owner@e.ru"]


# --- выгрузка ---

def test_csv_export_carries_the_rows_and_is_itself_recorded(client, auth_headers):
    """Вынос следов наружу — тоже событие, и о нём журнал иначе умолчал бы."""
    org = _seed(client, auth_headers)
    r = client.get(f"/api/v1/organizations/{org}/audit-log.csv", headers=auth_headers)
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    assert text.startswith("Дата и время;Кто;Действие")   # Excel в русской локали
    assert "project.create" in text and "Завод" in text

    actions = [e["action"] for e in _log(client, auth_headers, org)["entries"]]
    assert "audit_log.export" in actions


def test_csv_export_respects_the_same_filter_as_the_screen(client, auth_headers):
    org = _seed(client, auth_headers)
    text = client.get(f"/api/v1/organizations/{org}/audit-log.csv",
                      params={"action": "project.create"},
                      headers=auth_headers).content.decode("utf-8-sig")
    assert "Завод" in text and "Склад" in text
    assert "case.create" not in text


def test_journal_is_for_managers_only(client, auth_headers, register):
    org = _org(client, auth_headers)
    outsider = register(email="чужой@e.ru", org="Чужая")
    assert client.get(f"/api/v1/organizations/{org}/audit-log.csv",
                      headers=outsider).status_code == 403


# --- события входа ---

def test_login_is_recorded_in_the_organizations_of_the_user(client, auth_headers):
    org = _org(client, auth_headers)
    client.post("/api/v1/auth/login", json={"email": "owner@e.ru", "password": "secret123"})
    actions = [e["action"] for e in _log(client, auth_headers, org)["entries"]]
    assert "auth.login" in actions


def test_failed_login_of_a_known_user_is_recorded(client, auth_headers):
    """Подбор пароля виден только так."""
    org = _org(client, auth_headers)
    client.post("/api/v1/auth/login", json={"email": "owner@e.ru", "password": "неверный"})
    entry = next(e for e in _log(client, auth_headers, org)["entries"]
                 if e["action"] == "auth.login_failed")
    assert entry["actor_email"] == "owner@e.ru"


def test_unknown_address_leaves_no_trace(client, auth_headers):
    """Иначе журнал становится подсказчиком «такой адрес у нас есть»."""
    org = _org(client, auth_headers)
    before = _log(client, auth_headers, org)["total"]
    client.post("/api/v1/auth/login",
                json={"email": "не-существует@e.ru", "password": "любой"})
    assert _log(client, auth_headers, org)["total"] == before


def test_password_change_is_recorded_with_its_failure(client, auth_headers):
    org = _org(client, auth_headers)
    client.post("/api/v1/auth/password",
                json={"current_password": "неверный", "new_password": "newsecret123"},
                headers=auth_headers)
    client.post("/api/v1/auth/password",
                json={"current_password": "secret123", "new_password": "newsecret123"},
                headers=auth_headers)
    actions = [e["action"] for e in _log(client, auth_headers, org)["entries"]]
    assert "auth.password_change" in actions
    assert "auth.password_change_failed" in actions


def test_billing_changes_are_recorded(client, auth_headers):
    """Смена тарифа — деньги и квоты организации, а раньше не писалась вовсе."""
    org = _org(client, auth_headers)
    client.post(f"/api/v1/organizations/{org}/subscription",
                json={"plan_code": "team"}, headers=auth_headers)
    actions = [e["action"] for e in _log(client, auth_headers, org)["entries"]]
    assert "billing.plan_change" in actions
