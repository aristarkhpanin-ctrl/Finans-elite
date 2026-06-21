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
    AutoFinancing,
    Company,
    Deposit,
    DirectCostLine,
    Environment,
    EquityInjection,
    Financing,
    FixedCostLine,
    InvestmentPlan,
    Lease,
    Loan,
    OperatingPlan,
    PaymentTerms,
    Product,
    ProductionLine,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.models.common import (
    CostFunction,
    DirectCostKind,
    InventoryMethod,
    RepaymentType,
    VatBasis,
)
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

    def terms() -> PaymentTerms:
        return PaymentTerms(
            prepayment_share=Decimal(rng.randint(0, 100)) / Decimal(100),
            advance_lead_months=rng.randint(0, 3),
            payment_delay_months=rng.randint(0, 4),
        )

    n_products = rng.randint(1, 3)
    sales = [
        SalesLine(product_id=f"p{i}", volume=series(0, 200), price=series(10, 500),
                  payment=terms(), foreign=rng.random() < 0.3)
        for i in range(n_products)
    ]
    # план производства (для части продуктов) — образует запасы готовой продукции
    production = [
        ProductionLine(product_id=f"p{i}", volume=series(0, 200))
        for i in range(n_products)
        if rng.random() < 0.5
    ]
    direct = [
        DirectCostLine(name="m", kind=DirectCostKind.MATERIALS, amount=series(0, 30000),
                       payment_delay_months=rng.randint(0, 4),
                       stock_lead_months=rng.randint(0, 3)),
        DirectCostLine(name="w", kind=DirectCostKind.PIECE_WAGES, amount=series(0, 10000),
                       payment_delay_months=rng.randint(0, 2)),
    ]
    fixed = [
        FixedCostLine(name=f"f{i}", function=rng.choice(list(CostFunction)), amount=series(0, 20000),
                      payment_delay_months=rng.randint(0, 3), from_profit=rng.random() < 0.3,
                      foreign=rng.random() < 0.3)
        for i in range(rng.randint(0, 3))
    ]
    assets = []
    for i in range(rng.randint(0, 3)):
        pm = rng.randint(0, n - 1)
        sell = rng.random() < 0.3
        assets.append(Asset(
            name=f"a{i}",
            cost=Decimal(rng.randint(10000, 500000)),
            purchase_month=pm,
            life_months=rng.randint(1, 36),
            sale_month=(rng.randint(pm, n - 1) if sell else None),
            sale_price=(Decimal(rng.randint(0, 500000)) if sell else Decimal(0)),
        ))
    loans = [
        Loan(
            name=f"l{i}",
            amount=Decimal(rng.randint(10000, 300000)),
            start_month=rng.randint(0, n - 1),
            term_months=rng.randint(1, 24),
            annual_rate=Decimal(rng.randint(0, 30)) / Decimal(100),
            repayment=rng.choice(list(RepaymentType)),
            interest_on_profit=rng.random() < 0.3,
            foreign=rng.random() < 0.3,
        )
        for i in range(rng.randint(0, 2))
    ]
    equity = [
        EquityInjection(amount=Decimal(rng.randint(10000, 500000)), month=rng.randint(0, n - 1))
        for _ in range(rng.randint(0, 2))
    ]
    leases = [
        Lease(name=f"ls{i}", monthly_payment=Decimal(rng.randint(0, 20000)),
              start_month=rng.randint(0, n - 1), term_months=rng.randint(1, 24))
        for i in range(rng.randint(0, 2))
    ]
    deposits = [
        Deposit(name=f"dp{i}", amount=Decimal(rng.randint(0, 200000)),
                start_month=rng.randint(0, n - 1), term_months=rng.randint(1, 24),
                annual_rate=Decimal(rng.randint(0, 20)) / Decimal(100))
        for i in range(rng.randint(0, 2))
    ]
    dividends = [Decimal(rng.randint(0, 5000)) for _ in range(n)]

    auto = AutoFinancing(
        enabled=rng.random() < 0.5,
        annual_rate=Decimal(rng.randint(0, 30)) / Decimal(100),
        min_balance=Decimal(rng.randint(0, 5000)),
    )
    # Валютная позиция: опорный актив во 2-й валюте, уравновешенный капиталом; курс гуляет.
    fx_open = Decimal(rng.randint(40, 80))
    fx_rate = [Decimal(rng.randint(30, 100)) for _ in range(n)]
    fm = Decimal(rng.randint(0, 1000))
    company = Company(starting_balance=StartingBalance(
        foreign_monetary=fm, paid_in_capital=fm * fx_open))
    return ProjectModel(
        header=ProjectHeader(duration_months=n),
        company=company,
        environment=Environment(fx_open=fx_open, fx_rate=fx_rate),
        settings=ProjectSettings(
            discount_rate_annual=Decimal("0.15"),
            profit_tax_rate=Decimal(rng.randint(0, 30)) / Decimal(100),
            profit_tax_benefit_share=Decimal(rng.randint(0, 50)) / Decimal(100),
            payroll_contribution_rate=Decimal(rng.randint(0, 40)) / Decimal(100),
            inflation_sales=Decimal(rng.randint(0, 20)) / Decimal(100),
            inflation_direct=Decimal(rng.randint(0, 20)) / Decimal(100),
            inflation_wages=Decimal(rng.randint(0, 20)) / Decimal(100),
            inflation_general=Decimal(rng.randint(0, 20)) / Decimal(100),
            property_tax_rate=Decimal(rng.randint(0, 3)) / Decimal(100),
            vat_rate=rng.choice([Decimal(0), Decimal("0.10"), Decimal("0.20")]),
            vat_basis=rng.choice(list(VatBasis)),
            inventory_method=rng.choice(list(InventoryMethod)),
        ),
        operating_plan=OperatingPlan(
            products=[Product(id=s.product_id, name=s.product_id) for s in sales],
            sales=sales,
            production=production,
            direct_costs=direct,
            fixed_costs=fixed,
        ),
        investment_plan=InvestmentPlan(assets=assets),
        financing=Financing(loans=loans, leases=leases, deposits=deposits, equity=equity,
                            dividends=dividends, auto_financing=auto),
    )


@pytest.mark.parametrize("seed", range(50))
def test_random_projects_balance(seed):
    """50 псевдослучайных проектов: баланс обязан сходиться во всех периодах."""
    rng = random.Random(seed)
    model = _random_project(rng)
    result = run(model)  # сам по себе бросит InvariantError при нарушении
    _assert_balances(result)
