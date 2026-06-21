"""Тесты анализа чувствительности (7.3)."""
from decimal import Decimal

import pytest

from calc_core import run
from calc_core.samples import build_sample_project
from calc_core.sensitivity import run_sensitivity


def test_factor_one_matches_base_npv():
    model = build_sample_project()
    base = run(model).metrics.npv
    points = run_sensitivity(model, "sales_price", [Decimal("1.0")])
    assert points[0].npv == base


def test_higher_price_increases_npv():
    points = run_sensitivity(build_sample_project(), "sales_price",
                             [Decimal("0.8"), Decimal("1.0"), Decimal("1.2")])
    assert points[0].npv < points[1].npv < points[2].npv


def test_higher_direct_costs_decrease_npv():
    points = run_sensitivity(build_sample_project(), "direct_costs",
                             [Decimal("0.8"), Decimal("1.2")])
    assert points[0].npv > points[1].npv


def test_unknown_param_raises():
    with pytest.raises(ValueError):
        run_sensitivity(build_sample_project(), "magic", [Decimal("1.0")])


def test_does_not_mutate_original_model():
    model = build_sample_project()
    before = [list(s.price) for s in model.operating_plan.sales]
    run_sensitivity(model, "sales_price", [Decimal("2.0")])
    after = [list(s.price) for s in model.operating_plan.sales]
    assert before == after  # исходная модель не изменена


def test_sensitivity_api(client, auth_headers):
    sample = client.get("/api/v1/sample").json()
    pid = client.post("/api/v1/projects", json={"name": "S", "model": sample},
                      headers=auth_headers).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/sensitivity",
                    json={"param": "sales_price", "factors": ["0.9", "1.1"]}, headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["points"]) == 2


def test_sensitivity_api_invalid_param(client, auth_headers):
    sample = client.get("/api/v1/sample").json()
    pid = client.post("/api/v1/projects", json={"name": "S", "model": sample},
                      headers=auth_headers).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/sensitivity",
                    json={"param": "nope", "factors": ["1.0"]}, headers=auth_headers)
    assert r.status_code == 422
