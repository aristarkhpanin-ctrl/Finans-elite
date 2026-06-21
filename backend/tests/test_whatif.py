"""Тесты What-If анализа (9.1)."""
from decimal import Decimal

import pytest

from calc_core import run
from calc_core.samples import build_sample_project
from calc_core.whatif import Scenario, ScenarioAdjustment, run_what_if


def test_base_scenario_matches_run():
    model = build_sample_project()
    base_npv = run(model).metrics.npv
    results = run_what_if(model, [])
    assert results[0].name == "Базовый"
    assert results[0].npv == base_npv


def test_scenarios_compared():
    results = run_what_if(build_sample_project(), [
        Scenario("Оптимистичный", [ScenarioAdjustment("sales_price", Decimal("1.2"))]),
        Scenario("Пессимистичный", [ScenarioAdjustment("sales_price", Decimal("0.8"))]),
    ])
    names = [r.name for r in results]
    assert names == ["Базовый", "Оптимистичный", "Пессимистичный"]
    base, opt, pess = results
    assert pess.npv < base.npv < opt.npv


def test_scenario_combines_adjustments():
    # цена ↑ и издержки ↓ одновременно → NPV выше базового
    results = run_what_if(build_sample_project(), [
        Scenario("Двойной эффект", [
            ScenarioAdjustment("sales_price", Decimal("1.1")),
            ScenarioAdjustment("direct_costs", Decimal("0.9")),
        ]),
    ])
    assert results[1].npv > results[0].npv


def test_unknown_param_raises():
    with pytest.raises(ValueError):
        run_what_if(build_sample_project(), [Scenario("X", [ScenarioAdjustment("magic", Decimal("1"))])])


def test_what_if_api(client, auth_headers):
    sample = client.get("/api/v1/sample").json()
    pid = client.post("/api/v1/projects", json={"name": "WI", "model": sample},
                      headers=auth_headers).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/what-if", json={"scenarios": [
        {"name": "Рост цен", "adjustments": [{"param": "sales_price", "factor": "1.15"}]},
    ]}, headers=auth_headers)
    assert r.status_code == 200
    scen = r.json()["scenarios"]
    assert [s["name"] for s in scen] == ["Базовый", "Рост цен"]
