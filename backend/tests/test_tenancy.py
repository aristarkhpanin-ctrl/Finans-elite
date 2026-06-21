"""Тесты мультиарендности (6.2): организации, членство, изоляция проектов."""


def _org(client, name: str) -> str:
    return client.post("/api/v1/organizations", json={"name": name}).json()["id"]


def _sample(client) -> dict:
    return client.get("/api/v1/sample").json()


def test_create_organization_and_member(client):
    org_id = _org(client, "Акме")
    assert client.get(f"/api/v1/organizations/{org_id}").json()["name"] == "Акме"
    r = client.post(f"/api/v1/organizations/{org_id}/members",
                    json={"email": "a@e.ru", "full_name": "Аналитик", "role": "owner"})
    assert r.status_code == 201
    assert r.json()["email"] == "a@e.ru"
    assert len(client.get(f"/api/v1/organizations/{org_id}/members").json()) == 1


def test_projects_isolated_between_orgs(client):
    org_a = _org(client, "A")
    org_b = _org(client, "B")
    ha = {"X-Organization-Id": org_a}
    hb = {"X-Organization-Id": org_b}

    pid = client.post("/api/v1/projects", json={"name": "секрет A", "model": _sample(client)},
                      headers=ha).json()["id"]

    # организация B не видит проект A
    assert client.get(f"/api/v1/projects/{pid}", headers=hb).status_code == 404
    assert client.get("/api/v1/projects", headers=hb).json() == []
    # организация A видит свой проект
    assert len(client.get("/api/v1/projects", headers=ha).json()) == 1
    # B не может удалить/рассчитать чужой проект
    assert client.delete(f"/api/v1/projects/{pid}", headers=hb).status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/calculate", headers=hb).status_code == 404


def test_missing_org_header_422(client):
    # отсутствие X-Organization-Id — ошибка валидации заголовка
    assert client.get("/api/v1/projects").status_code == 422


def test_unknown_org_404(client):
    assert client.get("/api/v1/projects", headers={"X-Organization-Id": "unknown-id"}).status_code == 404


def test_member_added_once(client):
    org_id = _org(client, "Орг")
    client.post(f"/api/v1/organizations/{org_id}/members", json={"email": "u@e.ru"})
    client.post(f"/api/v1/organizations/{org_id}/members", json={"email": "u@e.ru"})
    # повторное добавление того же email не создаёт дубль членства
    assert len(client.get(f"/api/v1/organizations/{org_id}/members").json()) == 1
