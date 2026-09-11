"""Тесты API ревью бизнес-плана (Ф10): GET /projects/{id}/review."""


def _project(client, headers, name="Ревью"):
    sample = client.get("/api/v1/sample").json()
    return client.post("/api/v1/projects", json={"name": name, "model": sample},
                       headers=headers).json()["id"]


def test_review_endpoint_returns_findings(client, auth_headers):
    pid = _project(client, auth_headers)
    r = client.get(f"/api/v1/projects/{pid}/review", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["light"] in {"ok", "info", "warning", "risk"}
    assert set(body["counts"]) == {"risk", "warning", "info"}
    assert sum(body["counts"].values()) == len(body["findings"])
    assert body["deep"] is False
    # демо «Мини-производство» маргинально → есть risk-находка жизнеспособности
    assert body["light"] == "risk"
    assert "viability.npv_negative" in {f["id"] for f in body["findings"]}
    # находка содержит человекочитаемый текст и обоснование
    f0 = body["findings"][0]
    assert f0["title"] and f0["recommendation"] and f0["severity"] in {"info", "warning", "risk"}
    # экспертное заключение (D0): связный текст с вердиктом по маргинальному демо
    assert "не рекомендуется" in body["opinion"]
    assert "NPV" in body["opinion"]


def test_review_deep_runs_divergence(client, auth_headers):
    pid = _project(client, auth_headers)
    r = client.get(f"/api/v1/projects/{pid}/review?deep=true", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["deep"] is True
    assert sum(body["counts"].values()) == len(body["findings"])   # стохастика не ломает ответ


def test_review_missing_project_404(client, auth_headers):
    assert client.get("/api/v1/projects/nope/review", headers=auth_headers).status_code == 404


def test_review_isolated_from_other_tenant(client, register):
    owner = register(email="a@e.ru", org="A")
    other = register(email="b@e.ru", org="B")
    pid = _project(client, owner)
    assert client.get(f"/api/v1/projects/{pid}/review", headers=other).status_code == 404


def test_review_requires_auth(client, auth_headers):
    pid = _project(client, auth_headers)
    assert client.get(f"/api/v1/projects/{pid}/review").status_code in (401, 403)
