"""Журнал действий организации (152-ФЗ, ARCHITECTURE §4).

Обратный пробел сверки хендоффа: журнал доступа был на макете «Экран 11» и в
архитектуре, но таблицы в коде не существовало.
"""
from __future__ import annotations


def _org(client, headers) -> str:
    """Идентификатор организации пользователя (у зарегистрированного она одна)."""
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _log(client, headers, org_id):
    return client.get(f"/api/v1/organizations/{org_id}/audit-log", headers=headers)


def test_member_actions_are_recorded(client, register):
    """Приглашение, смена роли и удаление участника попадают в журнал."""
    owner = register(email="owner@e.ru", org="Орг Ж")
    oid = _org(client, owner)

    client.post(f"/api/v1/organizations/{oid}/members",
                json={"email": "an@e.ru", "full_name": "Аналитик", "role": "analyst"},
                headers=owner)
    uid = next(m["user_id"] for m in client.get(
        f"/api/v1/organizations/{oid}/members", headers=owner).json()
        if m["email"] == "an@e.ru")
    client.patch(f"/api/v1/organizations/{oid}/members/{uid}",
                 json={"role": "editor"}, headers=owner)
    client.delete(f"/api/v1/organizations/{oid}/members/{uid}", headers=owner)

    page = _log(client, owner, oid).json()
    actions = [e["action"] for e in page["entries"]]
    assert actions == ["member.remove", "member.role_change", "member.add"]  # новые сверху
    assert page["total"] == 3

    # запись называет и объект, и суть изменения
    role_change = next(e for e in page["entries"] if e["action"] == "member.role_change")
    assert role_change["entity_name"] == "an@e.ru"
    assert role_change["details"] == "analyst → editor"
    assert role_change["actor_email"] == "owner@e.ru"


def test_log_survives_member_removal(client, register):
    """Запись остаётся осмысленной после ухода участника.

    Почта актора хранится текстом рядом со ссылкой: журнал обязан отвечать «кто это
    сделал» и через год после увольнения, когда ссылка уже никуда не ведёт.
    """
    owner = register(email="o2@e.ru", org="Орг Ж2")
    oid = _org(client, owner)
    client.post(f"/api/v1/organizations/{oid}/members",
                json={"email": "gone@e.ru", "full_name": "Ушёл", "role": "analyst"},
                headers=owner)
    uid = next(m["user_id"] for m in client.get(
        f"/api/v1/organizations/{oid}/members", headers=owner).json()
        if m["email"] == "gone@e.ru")
    client.delete(f"/api/v1/organizations/{oid}/members/{uid}", headers=owner)

    entries = _log(client, owner, oid).json()["entries"]
    assert all(e["actor_email"] == "o2@e.ru" for e in entries)
    assert any(e["entity_name"] == "gone@e.ru" for e in entries)


def test_log_is_isolated_by_organization(client, register):
    """Чужой журнал недоступен: это следы работы другого арендатора."""
    a = register(email="a5@e.ru", org="Орг A5")
    b = register(email="b5@e.ru", org="Орг B5")
    oid_a = _org(client, a)
    client.post(f"/api/v1/organizations/{oid_a}/members",
                json={"email": "x@e.ru", "full_name": "", "role": "viewer"}, headers=a)

    assert _log(client, b, oid_a).status_code == 403
    assert _log(client, a, oid_a).json()["total"] == 1


def test_log_requires_org_manage(client, register):
    """Журнал видит только тот, кто управляет организацией (право org.manage).

    Аналитик работает с делами, но следы чужой работы — не его дело.
    """
    owner = register(email="o3@e.ru", org="Орг Ж3")
    analyst = register(email="an3@e.ru", org="Своя орг")   # уже существующий пользователь
    oid = _org(client, owner)
    client.post(f"/api/v1/organizations/{oid}/members",
                json={"email": "an3@e.ru", "full_name": "", "role": "analyst"},
                headers=owner)

    assert _log(client, analyst, oid).status_code == 403
    assert _log(client, owner, oid).status_code == 200


def test_log_has_no_write_endpoints():
    """У журнала нет ни правки, ни удаления — иначе это не журнал.

    Проверяется по контракту приложения, а не попыткой запроса: отсутствие операции и
    запрет на неё — разные вещи, и убедиться надо именно в отсутствии.
    """
    from app.main import app
    paths = app.openapi()["paths"]
    log = {p: set(ops) for p, ops in paths.items() if p.endswith("/audit-log")}
    assert log == {"/api/v1/organizations/{org_id}/audit-log": {"get"}}


def test_log_pagination_caps_limit(client, register):
    """Запрошенный лимит ограничивается сверху: журнал не выгружается одним запросом."""
    owner = register(email="o4@e.ru", org="Орг Ж4")
    oid = _org(client, owner)
    r = client.get(f"/api/v1/organizations/{oid}/audit-log?limit=100000", headers=owner)
    assert r.status_code == 200 and len(r.json()["entries"]) <= 500


def _case(client, headers):
    model = {"name": "ООО «Цель»", "currency": "RUB", "industry": "Торговля",
             "periods": [{"label": "2024", "kind": "year"}],
             "balance": {"A_CASH": ["10"], "P_EQUITY": ["10"]}, "income": {}}
    return client.post("/api/v1/audit/subjects",
                       json={"name": "ООО «Цель»", "model": model}, headers=headers).json()


def test_case_lifecycle_is_recorded(client, register):
    """Заведение, дубль, выгрузка и удаление дела попадают в журнал.

    Выгрузка документа записывается наравне с правками: именно так отчётность цели
    покидает контур, и для 152-ФЗ это событие важнее половины изменений.
    """
    owner = register(email="c1@e.ru", org="Орг Д")
    oid = _org(client, owner)
    case = _case(client, owner)
    client.post(f"/api/v1/audit/subjects/{case['id']}/duplicate", headers=owner)
    client.get(f"/api/v1/audit/subjects/{case['id']}/report.docx", headers=owner)
    client.delete(f"/api/v1/audit/subjects/{case['id']}", headers=owner)

    actions = [e["action"] for e in _log(client, owner, oid).json()["entries"]]
    assert actions == ["case.delete", "case.export", "case.duplicate", "case.create"]


def test_deleted_case_is_still_named_in_the_log(client, register):
    """Запись об удалении называет исчезнувшее дело.

    Имя запоминается до удаления: после него журнал уже не смог бы сказать, что именно
    пропало, — а это главное, что от такой записи и нужно.
    """
    owner = register(email="c2@e.ru", org="Орг Д2")
    oid = _org(client, owner)
    case = _case(client, owner)
    client.delete(f"/api/v1/audit/subjects/{case['id']}", headers=owner)

    entry = next(e for e in _log(client, owner, oid).json()["entries"]
                 if e["action"] == "case.delete")
    assert entry["entity_name"] == "ООО «Цель»" and entry["entity_id"] == case["id"]


def test_demo_case_is_marked_in_the_log(client, register):
    owner = register(email="c3@e.ru", org="Орг Д3")
    oid = _org(client, owner)
    client.post("/api/v1/audit/subjects/demo", headers=owner)
    entry = _log(client, owner, oid).json()["entries"][0]
    assert entry["action"] == "case.create" and entry["details"] == "демо-дело"
