"""Тесты тарифов, подписки и контроля квот (6.5a)."""


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _sample(client):
    return client.get("/api/v1/sample").json()


def test_list_plans(client):
    codes = {p["code"] for p in client.get("/api/v1/plans").json()}
    assert {"free", "team", "business"} <= codes


def test_new_org_has_free_subscription(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    sub = client.get(f"/api/v1/organizations/{org_id}/subscription", headers=auth_headers).json()
    assert sub["plan_code"] == "free"
    assert sub["used_members"] == 1   # владелец
    assert sub["used_projects"] == 0


def test_change_plan_owner(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    r = client.post(f"/api/v1/organizations/{org_id}/subscription",
                    json={"plan_code": "team"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["plan_code"] == "team"
    assert r.json()["max_projects"] == 50


def test_change_plan_invalid_422(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    r = client.post(f"/api/v1/organizations/{org_id}/subscription",
                    json={"plan_code": "gold"}, headers=auth_headers)
    assert r.status_code == 422


def test_non_owner_cannot_change_plan(client, register):
    owner = register("owner@e.ru", "Owner Org")
    org_id = client.post("/api/v1/organizations", json={"name": "Команда"}, headers=owner).json()["id"]
    viewer = register("v@e.ru", "personal")
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": "v@e.ru", "role": "viewer"}, headers={**owner, "X-Organization-Id": org_id})
    vh = {**viewer, "X-Organization-Id": org_id}
    r = client.post(f"/api/v1/organizations/{org_id}/subscription",
                    json={"plan_code": "team"}, headers=vh)
    assert r.status_code == 403


def test_project_quota_enforced(client, auth_headers):
    sample = _sample(client)
    for i in range(5):  # тариф free: 5 проектов
        assert client.post("/api/v1/projects", json={"name": f"P{i}", "model": sample},
                           headers=auth_headers).status_code == 201
    # шестой превышает лимит
    r = client.post("/api/v1/projects", json={"name": "P5", "model": sample}, headers=auth_headers)
    assert r.status_code == 402


def test_quota_lifted_after_upgrade(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    sample = _sample(client)
    for i in range(5):
        client.post("/api/v1/projects", json={"name": f"P{i}", "model": sample}, headers=auth_headers)
    assert client.post("/api/v1/projects", json={"name": "over", "model": sample},
                       headers=auth_headers).status_code == 402
    # апгрейд на team снимает лимит
    client.post(f"/api/v1/organizations/{org_id}/subscription",
                json={"plan_code": "team"}, headers=auth_headers)
    assert client.post("/api/v1/projects", json={"name": "ok", "model": sample},
                       headers=auth_headers).status_code == 201


def test_member_quota_enforced(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    h = auth_headers  # владелец уже 1 участник; лимит free = 5
    for i in range(4):  # добавляем до 5 участников
        assert client.post(f"/api/v1/organizations/{org_id}/members",
                           json={"email": f"u{i}@e.ru", "role": "viewer"}, headers=h).status_code == 201
    # шестой участник превышает лимит
    r = client.post(f"/api/v1/organizations/{org_id}/members",
                    json={"email": "extra@e.ru", "role": "viewer"}, headers=h)
    assert r.status_code == 402
