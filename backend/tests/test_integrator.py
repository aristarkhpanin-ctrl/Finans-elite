"""Тесты Integrator — консолидации проектов (9.2)."""
from decimal import Decimal

import pytest

from calc_core import run
from calc_core.integrator import consolidate
from calc_core.samples import build_sample_project


def test_consolidate_sums_statements():
    a = build_sample_project()
    b = build_sample_project()
    ra, rb = run(a), run(b)
    group = consolidate([a, b])
    # построчная сумма: выручка группы = сумма выручек
    for t in range(group.n):
        assert group.income["I1"][t] == ra.income["I1"][t] + rb.income["I1"][t]
        assert group.balance["B20"][t] == ra.balance["B20"][t] + rb.balance["B20"][t]


def test_consolidated_balance_invariant():
    group = consolidate([build_sample_project(), build_sample_project()])
    for t in range(group.n):
        assert abs(group.balance["B20"][t] - group.balance["B34"][t]) <= Decimal("0.01")


def test_consolidate_requires_same_duration():
    a = build_sample_project()
    b = build_sample_project()
    b.header.duration_months = 6
    with pytest.raises(ValueError):
        consolidate([a, b])


def test_consolidate_empty_raises():
    with pytest.raises(ValueError):
        consolidate([])


def test_integrator_api(client, auth_headers):
    sample = client.get("/api/v1/sample").json()
    p1 = client.post("/api/v1/projects", json={"name": "П1", "model": sample}, headers=auth_headers).json()["id"]
    p2 = client.post("/api/v1/projects", json={"name": "П2", "model": sample}, headers=auth_headers).json()["id"]
    r = client.post("/api/v1/integrator/consolidate",
                    json={"project_ids": [p1, p2]}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    b20 = next(l for l in data["balance"]["lines"] if l["code"] == "B20")["values"]
    b34 = next(l for l in data["balance"]["lines"] if l["code"] == "B34")["values"]
    for x, y in zip(b20, b34):
        assert abs(Decimal(x) - Decimal(y)) <= Decimal("0.01")


def test_integrator_api_missing_project_404(client, auth_headers):
    r = client.post("/api/v1/integrator/consolidate",
                    json={"project_ids": ["nope"]}, headers=auth_headers)
    assert r.status_code == 404
