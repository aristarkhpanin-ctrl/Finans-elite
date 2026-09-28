"""Тесты API сметы по этапам (календарный план): GET /projects/{id}/budget."""


def _project_with_stage(client, headers):
    model = {
        "header": {"duration_months": 4},
        "investment_plan": {"calendar": {"stages": [
            {"id": "s1", "name": "Лицензия", "kind": "expense",
             "start_month": 0, "duration_months": 2, "cost": "600"},
        ]}},
    }
    return client.post("/api/v1/projects", json={"name": "Смета", "model": model},
                       headers=headers).json()["id"]


def test_budget_endpoint_returns_estimate(client, auth_headers):
    pid = _project_with_stage(client, auth_headers)
    r = client.get(f"/api/v1/projects/{pid}/budget", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert float(body["total"]) == 600
    assert len(body["stages"]) == 1 and body["stages"][0]["id"] == "s1"
    assert [float(x) for x in body["monthly"]] == [300, 300, 0, 0]  # 600/2 равномерно


def test_budget_empty_for_sample(client, auth_headers):
    sample = client.get("/api/v1/sample").json()
    pid = client.post("/api/v1/projects", json={"name": "S", "model": sample},
                      headers=auth_headers).json()["id"]
    body = client.get(f"/api/v1/projects/{pid}/budget", headers=auth_headers).json()
    assert body["stages"] == [] and float(body["total"]) == 0


def test_budget_404_and_isolation(client, register):
    owner = register(email="a@e.ru", org="A")
    other = register(email="b@e.ru", org="B")
    pid = _project_with_stage(client, owner)
    assert client.get(f"/api/v1/projects/{pid}/budget", headers=other).status_code == 404
    assert client.get("/api/v1/projects/nope/budget", headers=owner).status_code == 404


def test_budget_requires_auth(client, auth_headers):
    pid = _project_with_stage(client, auth_headers)
    assert client.get(f"/api/v1/projects/{pid}/budget").status_code in (401, 403)
