"""Тесты PIC Holding (9.3): структура и сводный бюджет."""
from decimal import Decimal


def _project(client, headers, name="П") -> str:
    sample = client.get("/api/v1/sample").json()
    return client.post("/api/v1/projects", json={"name": name, "model": sample},
                       headers=headers).json()["id"]


def test_create_holding_and_add_members(client, auth_headers):
    hid = client.post("/api/v1/holdings", json={"name": "Группа"}, headers=auth_headers).json()["id"]
    p1 = _project(client, auth_headers, "Голова")
    p2 = _project(client, auth_headers, "Дочка")
    client.post(f"/api/v1/holdings/{hid}/members",
                json={"project_id": p1, "role": "parent"}, headers=auth_headers)
    r = client.post(f"/api/v1/holdings/{hid}/members",
                    json={"project_id": p2, "role": "subsidiary"}, headers=auth_headers)
    assert r.status_code == 201
    members = {m["project_id"]: m["role"] for m in r.json()["members"]}
    assert members == {p1: "parent", p2: "subsidiary"}


def test_holding_consolidate_invariant(client, auth_headers):
    hid = client.post("/api/v1/holdings", json={"name": "Группа"}, headers=auth_headers).json()["id"]
    for nm in ("A", "B"):
        client.post(f"/api/v1/holdings/{hid}/members",
                    json={"project_id": _project(client, auth_headers, nm)}, headers=auth_headers)
    data = client.post(f"/api/v1/holdings/{hid}/consolidate", headers=auth_headers).json()
    b20 = next(l for l in data["balance"]["lines"] if l["code"] == "B20")["values"]
    b34 = next(l for l in data["balance"]["lines"] if l["code"] == "B34")["values"]
    for x, y in zip(b20, b34):
        assert abs(Decimal(x) - Decimal(y)) <= Decimal("0.01")


def test_consolidate_empty_holding_422(client, auth_headers):
    hid = client.post("/api/v1/holdings", json={"name": "Пустой"}, headers=auth_headers).json()["id"]
    assert client.post(f"/api/v1/holdings/{hid}/consolidate", headers=auth_headers).status_code == 422


def test_add_member_foreign_project_404(client, auth_headers):
    hid = client.post("/api/v1/holdings", json={"name": "Г"}, headers=auth_headers).json()["id"]
    r = client.post(f"/api/v1/holdings/{hid}/members",
                    json={"project_id": "no-such"}, headers=auth_headers)
    assert r.status_code == 404


def test_holding_isolated_between_orgs(client, register):
    ha = register("a@e.ru", "A")
    hb = register("b@e.ru", "B")
    hid = client.post("/api/v1/holdings", json={"name": "ОргA"}, headers=ha).json()["id"]
    # организация B не видит холдинг A
    assert client.get(f"/api/v1/holdings/{hid}", headers=hb).status_code == 404


def test_delete_holding(client, auth_headers):
    hid = client.post("/api/v1/holdings", json={"name": "Удалить"}, headers=auth_headers).json()["id"]
    assert client.delete(f"/api/v1/holdings/{hid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/holdings/{hid}", headers=auth_headers).status_code == 404
