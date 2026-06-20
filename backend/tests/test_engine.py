from decimal import Decimal

import pytest

from calc_core import ProjectModel, run
from calc_core.engine import ModelError
from calc_core.models import Company, StartingBalance
from calc_core.samples import build_sample_project


def test_sample_runs_and_shapes():
    model = build_sample_project()
    result = run(model)
    assert result.n == 12
    assert result.engine_version
    # все строки отчётов имеют длину N
    for stmt in (result.income, result.cashflow, result.balance, result.profit_use):
        for code in stmt.order:
            assert len(stmt[code]) == result.n


def test_income_subtotals_formula():
    result = run(build_sample_project())
    inc = result.income
    n = result.n
    for t in range(n):
        assert inc["I4"][t] == inc["I1"][t] - inc["I2"][t] - inc["I3"][t]
        assert inc["I7"][t] == inc["I5"][t] + inc["I6"][t]
        assert inc["I8"][t] == inc["I4"][t] - inc["I7"][t]
        assert inc["I28"][t] == inc["I23"][t] + inc["I25"][t] - inc["I27"][t]


def test_cashflow_closing_balance_recurrence():
    result = run(build_sample_project())
    cf = result.cashflow
    for t in range(result.n):
        expected = cf["C13"][t] + cf["C20"][t] + cf["C27"][t] + cf["C28"][t]
        assert cf["C29"][t] == expected


def test_revenue_matches_volume_price():
    result = run(build_sample_project())
    # 100 ед × 1000 = 100000 выручки в месяц
    assert result.income["I1"][0] == Decimal("100000")


def test_unbalanced_starting_balance_raises():
    bad = ProjectModel(
        company=Company(starting_balance=StartingBalance(cash=Decimal(100)))  # актив 100 ≠ пассив 0
    )
    with pytest.raises(ModelError):
        run(bad)
