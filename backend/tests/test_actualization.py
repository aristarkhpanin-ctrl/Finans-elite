"""Тесты актуализации (план-факт, 7.5)."""
from decimal import Decimal

import pytest

from calc_core import run
from calc_core.samples import build_sample_project


def test_no_actualization_is_none():
    r = run(build_sample_project())
    assert r.actualized_cashflow is None
    assert r.cashflow_variance is None


def test_actualization_applies_to_past_only():
    plan = run(build_sample_project())
    m = build_sample_project()
    m.actualization.actual_until = 2
    m.actualization.actuals = {"C1": [Decimal(200000)] * 12}
    r = run(m)
    # прошедшие периоды (0..2) — факт
    for t in range(3):
        assert r.actualized_cashflow["C1"][t] == Decimal(200000)
    # будущие (>=3) — план
    for t in range(3, r.n):
        assert r.actualized_cashflow["C1"][t] == plan.cashflow["C1"][t]


def test_variance_is_actual_minus_plan():
    plan = run(build_sample_project())
    m = build_sample_project()
    m.actualization.actual_until = 1
    m.actualization.actuals = {"C1": [Decimal(200000)] * 12}
    r = run(m)
    for t in range(r.n):
        assert r.cashflow_variance["C1"][t] == r.actualized_cashflow["C1"][t] - plan.cashflow["C1"][t]


def test_actualized_closing_balance_recomputed():
    plan = run(build_sample_project())
    m = build_sample_project()
    m.actualization.actual_until = 0
    # факт поступлений в месяце 0 больше плана на 100000 → сальдо C29 тоже больше
    actual_c1_0 = plan.cashflow["C1"][0] + Decimal(100000)
    m.actualization.actuals = {"C1": [actual_c1_0]}
    r = run(m)
    assert r.actualized_cashflow["C29"][0] == plan.cashflow["C29"][0] + Decimal(100000)


def test_invalid_actual_line_raises():
    m = build_sample_project()
    m.actualization.actual_until = 1
    m.actualization.actuals = {"C13": [Decimal(1)] * 12}  # вычисляемая строка — нельзя
    with pytest.raises(ValueError):
        run(m)


def test_actualization_api(client, auth_headers):
    sample = client.get("/api/v1/sample").json()
    sample["actualization"] = {"actual_until": 2, "actuals": {"C1": ["200000", "200000", "200000"]}}
    pid = client.post("/api/v1/projects", json={"name": "Факт", "model": sample},
                      headers=auth_headers).json()["id"]
    data = client.post(f"/api/v1/projects/{pid}/calculate", headers=auth_headers).json()
    assert data["actualized_cashflow"] is not None
    c1 = next(l for l in data["actualized_cashflow"]["lines"] if l["code"] == "C1")["values"]
    assert Decimal(c1[0]) == Decimal(200000)


def test_actualization_api_invalid_line_422(client, auth_headers):
    sample = client.get("/api/v1/sample").json()
    sample["actualization"] = {"actual_until": 1, "actuals": {"C29": ["1"]}}
    pid = client.post("/api/v1/projects", json={"name": "Факт", "model": sample},
                      headers=auth_headers).json()["id"]
    assert client.post(f"/api/v1/projects/{pid}/calculate", headers=auth_headers).status_code == 422
