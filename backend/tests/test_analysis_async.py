"""Тесты асинхронного анализа (Celery, eager-режим): submit → опрос → изоляция."""

_MC_BODY = {
    "iterations": 50, "seed": 42,
    "uncertain": [{"param": "sales_price", "distribution": {"kind": "uniform", "low": "0.8", "high": "1.2"}}],
}


def _project(client, headers):
    sample = client.get("/api/v1/sample").json()
    return client.post("/api/v1/projects", json={"name": "MC", "model": sample},
                       headers=headers).json()["id"]


def test_monte_carlo_async_success(client, auth_headers):
    pid = _project(client, auth_headers)
    submit = client.post(f"/api/v1/projects/{pid}/monte-carlo/async", json=_MC_BODY, headers=auth_headers)
    assert submit.status_code == 202
    job_id = submit.json()["job_id"]

    r = client.get(f"/api/v1/analysis/jobs/{job_id}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    # Результат совпадает по форме с синхронным Монте-Карло.
    assert body["result"]["iterations"] == 50
    assert {"npv_mean", "npv_sem", "npv_p5", "npv_cvar_5", "histogram"} <= body["result"].keys()


def test_async_matches_sync(client, auth_headers):
    pid = _project(client, auth_headers)
    sync = client.post(f"/api/v1/projects/{pid}/monte-carlo", json=_MC_BODY, headers=auth_headers).json()
    job_id = client.post(f"/api/v1/projects/{pid}/monte-carlo/async", json=_MC_BODY,
                         headers=auth_headers).json()["job_id"]
    async_res = client.get(f"/api/v1/analysis/jobs/{job_id}", headers=auth_headers).json()["result"]
    # Тот же seed → бит-в-бит те же числа (детерминизм).
    assert async_res["npv_mean"] == sync["npv_mean"]
    assert async_res["npv_p5"] == sync["npv_p5"]


def test_job_isolated_from_other_tenant(client, register):
    a = register(email="a@e.ru", org="A")
    b = register(email="b@e.ru", org="B")
    pid = _project(client, a)
    job_id = client.post(f"/api/v1/projects/{pid}/monte-carlo/async", json=_MC_BODY, headers=a).json()["job_id"]
    # Чужой арендатор не видит задачу.
    assert client.get(f"/api/v1/analysis/jobs/{job_id}", headers=b).status_code == 404
    # Владелец — видит.
    assert client.get(f"/api/v1/analysis/jobs/{job_id}", headers=a).status_code == 200


def test_unknown_job_404(client, auth_headers):
    assert client.get("/api/v1/analysis/jobs/does-not-exist", headers=auth_headers).status_code == 404
