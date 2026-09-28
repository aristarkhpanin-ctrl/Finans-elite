"""Тесты гейта финализации плана (Ф10, решение Q4): POST /projects/{id}/finalize."""
from calc_core.review.types import Finding, ReviewResult


def _project(client, headers, name="Финал"):
    sample = client.get("/api/v1/sample").json()
    return client.post("/api/v1/projects", json={"name": name, "model": sample},
                       headers=headers).json()["id"]


def test_finalize_blocked_by_risk_without_ack(client, auth_headers):
    pid = _project(client, auth_headers)          # демо маргинально → есть risk-находки
    r = client.post(f"/api/v1/projects/{pid}/finalize", json={"acknowledge": False},
                    headers=auth_headers)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "review_has_risks"
    assert detail["review"]["counts"]["risk"] > 0
    # проект остаётся черновиком
    assert client.get(f"/api/v1/projects/{pid}", headers=auth_headers).json()["status"] == "draft"


def test_finalize_with_ack_succeeds(client, auth_headers):
    pid = _project(client, auth_headers)
    r = client.post(f"/api/v1/projects/{pid}/finalize", json={"acknowledge": True},
                    headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "finalized" and body["finalized_at"]
    assert body["review"]["deep"] is True
    proj = client.get(f"/api/v1/projects/{pid}", headers=auth_headers).json()
    assert proj["status"] == "finalized"
    assert proj["finalized_review"]["light"] == "risk"      # снимок ревью сохранён
    assert proj["finalized_drift"] is False


def test_editing_model_resets_to_draft(client, auth_headers):
    pid = _project(client, auth_headers)
    client.post(f"/api/v1/projects/{pid}/finalize", json={"acknowledge": True}, headers=auth_headers)
    sample = client.get("/api/v1/sample").json()
    sample["header"]["name"] = "изменено"
    upd = client.put(f"/api/v1/projects/{pid}", json={"model": sample}, headers=auth_headers)
    assert upd.status_code == 200
    assert upd.json()["status"] == "draft"                  # правка снимает финализацию


def test_warnings_do_not_block(client, auth_headers, monkeypatch):
    # Гейт блокирует только risk; warning/info финализации не мешают.
    pid = _project(client, auth_headers)
    fake = ReviewResult(
        light="warning", counts={"risk": 0, "warning": 1, "info": 0},
        findings=[Finding(id="liquidity.x", category="liquidity", severity="warning",
                          title="t", detail="d", recommendation="r")],
    )
    monkeypatch.setattr("app.routers.projects.run_review", lambda *a, **k: fake)
    r = client.post(f"/api/v1/projects/{pid}/finalize", json={"acknowledge": False},
                    headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "finalized"


def test_finalize_isolated_and_authed(client, register):
    owner = register(email="a@e.ru", org="A")
    other = register(email="b@e.ru", org="B")
    pid = _project(client, owner)
    assert client.post(f"/api/v1/projects/{pid}/finalize", json={"acknowledge": True},
                       headers=other).status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/finalize",
                       json={"acknowledge": True}).status_code in (401, 403)
