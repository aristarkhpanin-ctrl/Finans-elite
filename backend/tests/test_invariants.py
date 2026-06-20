"""Инвариант-тесты: главная гарантия корректности — сходимость баланса (SPEC §16).

Если расчёт нарушит тождество B20 = B34, ``run()`` поднимет InvariantError — то есть
сам прогон случайных моделей уже является проверкой. Дополнительно сверяем явно.
"""
from __future__ import annotations

import random
from decimal import Decimal

import pytest

from calc_core import run
from calc_core.models import (
    Asset,
    DirectCostLine,
    EquityInjection,
    Financing,
    FixedCostLine,
    InvestmentPlan,
    Loan,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)
from calc_core.models.common import CostFunction, DirectCostKind, RepaymentType
from calc_core.samples import build_sample_project

EPS = Decimal("0.01")


def _assert_balances(result):
    for t in range(result.n):
        assert abs(result.balance["B20"][t] - result.balance["B34"][t]) <= EPS
        assert abs(result.balance["B1"][t] - result.cashflow["C29"][t]) <= EPS
        assert abs(result.balance["B32"][t] - result.profit_use["P7"][t]) <= EPS


def test_sample_invariants():
    _assert_balances(run(build_sample_project()))


def _random_project(rng: random.Random) -> ProjectModel:
    n = rng.randint(1, 24)

    def series(lo: int, hi: int) -> list[Decimal]:
        return [Decimal(rng.randint(lo, hi)) for _ in range(n)]

    sales = [
        SalesLine(product_id=f"p{i}", volume=series(0, 200), price=series(10, 500))
        for i in range(rng.randint(1, 3))
    ]
    direct = [
        DirectCostLine(name="m", kind=DirectCostKind.MATERIALS, amount=series(0, 30000)),
        DirectCostLine(name="w", kind=DirectCostKind.PIECE_WAGES, amount=series(0, 10000)),
    ]
    fixed = [
        FixedCostLine(name=f"f{i}", function=rng.choice(list(CostFunction)), amount=series(0, 20000))
        for i in range(rng.randint(0, 3))
    ]
    assets = [
        Asset(
            name=f"a{i}",
            cost=Decimal(rng.randint(10000, 500000)),
            purchase_month=rng.randint(0, n - 1),
            life_months=rng.randint(1, 36),
        )
        for i in range(rng.randint(0, 3))
    ]
    loans = [
        Loan(
            name=f"l{i}",
            amount=Decimal(rng.randint(10000, 300000)),
            start_month=rng.randint(0, n - 1),
            term_months=rng.randint(1, 24),
            annual_rate=Decimal(rng.randint(0, 30)) / Decimal(100),
            repayment=rng.choice(list(RepaymentType)),
        )
        for i in range(rng.randint(0, 2))
    ]
    equity = [
        EquityInjection(amount=Decimal(rng.randint(10000, 500000)), month=rng.randint(0, n - 1))
        for _ in range(rng.randint(0, 2))
    ]
    dividends = [Decimal(rng.randint(0, 5000)) for _ in range(n)]

    return ProjectModel(
        header=ProjectHeader(duration_months=n),
        settings=ProjectSettings(
            discount_rate_annual=Decimal("0.15"),
            profit_tax_rate=Decimal(rng.randint(0, 30)) / Decimal(100),
            property_tax_rate=Decimal(rng.randint(0, 3)) / Decimal(100),
        ),
        operating_plan=OperatingPlan(
            products=[Product(id=s.product_id, name=s.product_id) for s in sales],
            sales=sales,
            direct_costs=direct,
            fixed_costs=fixed,
        ),
        investment_plan=InvestmentPlan(assets=assets),
        financing=Financing(loans=loans, equity=equity, dividends=dividends),
    )


@pytest.mark.parametrize("seed", range(50))
def test_random_projects_balance(seed):
    """50 псевдослучайных проектов: баланс обязан сходиться во всех периодах."""
    rng = random.Random(seed)
    model = _random_project(rng)
    result = run(model)  # сам по себе бросит InvariantError при нарушении
    _assert_balances(result)
