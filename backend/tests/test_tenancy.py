"""Тесты мультиарендности и доступа (6.2 + 6.3): изоляция проектов между пользователями."""


def _sample(client) -> dict:
    return client.get("/api/v1/sample").json()


def test_projects_isolated_between_users(client, register):
    ha = register("a@e.ru", "A")
    hb = register("b@e.ru", "B")

    pid = client.post("/api/v1/projects", json={"name": "секрет A", "model": _sample(client)},
                      headers=ha).json()["id"]

    # пользователь B (другая организация) не видит проект A
    assert client.get(f"/api/v1/projects/{pid}", headers=hb).status_code == 404
    assert client.get("/api/v1/projects", headers=hb).json() == []
    # пользователь A видит свой проект
    assert len(client.get("/api/v1/projects", headers=ha).json()) == 1
    # B не может удалить/рассчитать чужой проект
    assert client.delete(f"/api/v1/projects/{pid}", headers=hb).status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/calculate", headers=hb).status_code == 404


def test_unauthenticated_project_access_denied(client):
    # без токена доступа — отказ
    assert client.get("/api/v1/projects").status_code in (401, 403)


def test_create_org_and_members(client, register, auth_headers):
    # создать дополнительную организацию (создатель — владелец)
    org = client.post("/api/v1/organizations", json={"name": "Вторая"}, headers=auth_headers).json()
    assert client.get(f"/api/v1/organizations/{org['id']}", headers=auth_headers).status_code == 200
    # добавить участника по email
    r = client.post(f"/api/v1/organizations/{org['id']}/members",
                    json={"email": "new@e.ru", "full_name": "Новый", "role": "editor"},
                    headers=auth_headers)
    assert r.status_code == 201
    members = client.get(f"/api/v1/organizations/{org['id']}/members", headers=auth_headers).json()
    # создатель (owner@e.ru) — владелец, плюс добавленный участник
    assert {m["email"] for m in members} == {"owner@e.ru", "new@e.ru"}


def test_non_member_cannot_access_org(client, register):
    ha = register("a@e.ru", "A")
    hb = register("b@e.ru", "B")
    org_a = client.post("/api/v1/organizations", json={"name": "ТолькоA"}, headers=ha).json()["id"]
    # B не участник организации A → 403
    assert client.get(f"/api/v1/organizations/{org_a}", headers=hb).status_code == 403


def test_select_org_via_header(client, register, auth_headers):
    # пользователь состоит в нескольких организациях; выбор через X-Organization-Id
    org2 = client.post("/api/v1/organizations", json={"name": "Вторая"}, headers=auth_headers).json()["id"]
    client.post("/api/v1/projects", json={"name": "во второй", "model": _sample(client)},
                headers={**auth_headers, "X-Organization-Id": org2})
    # без заголовка — организация по умолчанию (первая), проектов там нет
    assert client.get("/api/v1/projects", headers=auth_headers).json() == []
    # с заголовком второй организации — проект виден
    in_org2 = client.get("/api/v1/projects", headers={**auth_headers, "X-Organization-Id": org2})
    assert len(in_org2.json()) == 1


def test_access_foreign_org_via_header_403(client, register):
    ha = register("a@e.ru", "A")
    hb = register("b@e.ru", "B")
    org_b = client.post("/api/v1/organizations", json={"name": "Borg"}, headers=hb).json()["id"]
    # A не состоит в организации B → указание её в заголовке запрещено
    assert client.get("/api/v1/projects",
                      headers={**ha, "X-Organization-Id": org_b}).status_code == 403


# --- Дверь арендатора: её видно только тем, кто смотрит на сам вызов ---

def test_every_door_into_an_organization_enters_the_tenant(client, register,
                                                           monkeypatch):
    """Маршрут, знающий свою организацию, обязан назвать её **базе**.

    Найдено при подготовке «Активности команды»: арендатора выставлял только путь через
    членство (`current_org_id`). Маршруты, берущие организацию **из пути**, — журнал,
    ориентиры, чек-листы — этого не делали, и на PostgreSQL читались бы **пустыми**:
    таблицы под RLS, а арендатор не задан. На SQLite такого не увидеть (RLS там нет
    вовсе), поэтому проверка смотрит не на данные, а на сам вызов двери.
    """
    from app import deps

    entered: list[str] = []
    monkeypatch.setattr(deps, "set_tenant", lambda db, org_id: entered.append(org_id))

    headers = register()
    org = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]

    doors = [
        ("членство", lambda: client.get("/api/v1/projects", headers=headers)),
        ("путь + право", lambda: client.get(f"/api/v1/organizations/{org}/audit-log",
                                            headers=headers)),
        ("путь + членство", lambda: client.get(f"/api/v1/organizations/{org}/benchmarks",
                                               headers=headers)),
        ("чек-листы", lambda: client.get(f"/api/v1/organizations/{org}/checklists",
                                         headers=headers)),
    ]
    for name, call in doors:
        entered.clear()
        assert call().status_code == 200, name
        assert org in entered, f"дверь «{name}» не назвала арендатора базе"


def test_an_api_key_also_enters_its_tenant(client, register, monkeypatch):
    """Ключ называет свою организацию сам — и обязан назвать её базе так же."""
    from app import deps

    headers = register()
    org = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    token = client.post(f"/api/v1/organizations/{org}/api-keys", json={"name": "К"},
                        headers=headers).json()["token"]

    entered: list[str] = []
    monkeypatch.setattr(deps, "set_tenant", lambda db, org_id: entered.append(org_id))
    client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token}"})
    assert entered == [org]
