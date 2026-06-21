"""Тесты персистентности проектов (6.1) в контексте организации (6.2)."""
from decimal import Decimal


def _sample_model(client) -> dict:
    return client.get("/api/v1/sample").json()


def test_create_and_get_project(client, org_headers):
    r = client.post("/api/v1/projects", json={"name": "Мой проект", "model": _sample_model(client)},
                    headers=org_headers)
    assert r.status_code == 201
    pid = r.json()["id"]
    got = client.get(f"/api/v1/projects/{pid}", headers=org_headers)
    assert got.status_code == 200
    assert got.json()["model"]["header"]["duration_months"] == 12


def test_list_projects(client, org_headers):
    client.post("/api/v1/projects", json={"name": "A", "model": _sample_model(client)}, headers=org_headers)
    client.post("/api/v1/projects", json={"name": "B", "model": _sample_model(client)}, headers=org_headers)
    r = client.get("/api/v1/projects", headers=org_headers)
    assert {p["name"] for p in r.json()} == {"A", "B"}


def test_get_missing_404(client, org_headers):
    assert client.get("/api/v1/projects/nope", headers=org_headers).status_code == 404


def test_update_project(client, org_headers):
    pid = client.post("/api/v1/projects", json={"name": "Старое", "model": _sample_model(client)},
                      headers=org_headers).json()["id"]
    r = client.put(f"/api/v1/projects/{pid}", json={"name": "Новое"}, headers=org_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Новое"


def test_delete_project(client, org_headers):
    pid = client.post("/api/v1/projects", json={"name": "Удалить", "model": _sample_model(client)},
                      headers=org_headers).json()["id"]
    assert client.delete(f"/api/v1/projects/{pid}", headers=org_headers).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=org_headers).status_code == 404


def test_calculate_stored_project(client, org_headers):
    pid = client.post("/api/v1/projects", json={"name": "Расчёт", "model": _sample_model(client)},
                      headers=org_headers).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/calculate", headers=org_headers)
    assert r.status_code == 200
    data = r.json()
    b20 = next(l for l in data["balance"]["lines"] if l["code"] == "B20")["values"]
    b34 = next(l for l in data["balance"]["lines"] if l["code"] == "B34")["values"]
    for a, b in zip(b20, b34):
        assert abs(Decimal(a) - Decimal(b)) <= Decimal("0.01")


def test_create_invalid_model_422(client, org_headers):
    bad = {"name": "Плохой", "model": {"header": {"duration_months": 0}}}
    assert client.post("/api/v1/projects", json=bad, headers=org_headers).status_code == 422
