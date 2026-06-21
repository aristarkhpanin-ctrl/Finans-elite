"""Тесты Монте-Карло (7.4)."""
from decimal import Decimal

import pytest

from calc_core.montecarlo import (
    Distribution,
    MonteCarloConfig,
    UncertainParam,
    run_monte_carlo,
)
from calc_core.samples import build_sample_project


def _config(iterations=200, seed=42):
    return MonteCarloConfig(
        iterations=iterations, seed=seed,
        uncertain=[
            UncertainParam("sales_price", Distribution("uniform", low=Decimal("0.8"), high=Decimal("1.2"))),
            UncertainParam("direct_costs", Distribution("normal", mean=Decimal("1.0"), std=Decimal("0.1"))),
        ],
    )


def test_monte_carlo_basic_stats():
    res = run_monte_carlo(build_sample_project(), _config())
    assert res.iterations == 200
    assert res.npv_min <= res.npv_p10 <= res.npv_p50 <= res.npv_p90 <= res.npv_max
    assert Decimal(0) <= res.probability_npv_positive <= Decimal(1)
    assert res.npv_std >= 0


def test_monte_carlo_reproducible_with_seed():
    a = run_monte_carlo(build_sample_project(), _config(seed=7))
    b = run_monte_carlo(build_sample_project(), _config(seed=7))
    assert a.npv_mean == b.npv_mean and a.npv_std == b.npv_std


def test_monte_carlo_different_seed_differs():
    a = run_monte_carlo(build_sample_project(), _config(seed=1))
    b = run_monte_carlo(build_sample_project(), _config(seed=2))
    assert a.npv_mean != b.npv_mean


def test_no_uncertainty_gives_zero_std():
    cfg = MonteCarloConfig(iterations=50, seed=42, uncertain=[])
    res = run_monte_carlo(build_sample_project(), cfg)
    assert res.npv_min == res.npv_max               # все прогоны идентичны (точно)
    assert res.npv_std < Decimal("0.01")            # разброса практически нет


def test_unknown_param_raises():
    cfg = MonteCarloConfig(iterations=10, seed=1,
                           uncertain=[UncertainParam("magic", Distribution("uniform", low=Decimal("0.9"), high=Decimal("1.1")))])
    with pytest.raises(ValueError):
        run_monte_carlo(build_sample_project(), cfg)


def test_monte_carlo_api(client, auth_headers):
    sample = client.get("/api/v1/sample").json()
    pid = client.post("/api/v1/projects", json={"name": "MC", "model": sample},
                      headers=auth_headers).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/monte-carlo", json={
        "iterations": 100, "seed": 42,
        "uncertain": [{"param": "sales_price", "distribution": {"kind": "uniform", "low": "0.8", "high": "1.2"}}],
    }, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["iterations"] == 100
    assert "probability_npv_positive" in r.json()


def test_monte_carlo_api_iteration_limit(client, auth_headers):
    sample = client.get("/api/v1/sample").json()
    pid = client.post("/api/v1/projects", json={"name": "MC", "model": sample},
                      headers=auth_headers).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/monte-carlo",
                    json={"iterations": 99999, "uncertain": []}, headers=auth_headers)
    assert r.status_code == 422
