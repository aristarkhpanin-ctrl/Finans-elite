"""Тесты автоподбора финансирования (7.1)."""
from decimal import Decimal

from calc_core import run
from calc_core.engine.financing_auto import solve_credit_line
from calc_core.models import (
    AutoFinancing,
    DirectCostLine,
    Financing,
    FixedCostLine,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)
from calc_core.models.common import CostFunction, DirectCostKind

EPS = Decimal("0.01")


def test_solve_credit_line_covers_deficit():
    # t0: дефицит 100 → привлекаем 100; t1: проценты 1, гасим из профицита
    draws, principal, interest = solve_credit_line(
        [Decimal(-100), Decimal(60), Decimal(60)], Decimal(0), Decimal(0), Decimal("0.01")
    )
    assert draws[0] == Decimal(100)
    assert interest[0] == Decimal(0)            # на начало периода 0 долга нет
    assert interest[1] == Decimal(1)            # 100 × 1%
    assert principal[1] == Decimal(59)          # из профицита 60−1


def test_solve_credit_line_no_deficit_no_draws():
    draws, principal, interest = solve_credit_line(
        [Decimal(100), Decimal(50)], Decimal(0), Decimal(0), Decimal("0.01")
    )
    assert draws == [Decimal(0), Decimal(0)]
    assert interest == [Decimal(0), Decimal(0)]


def _deficit_project(auto: bool, min_balance: str = "0") -> ProjectModel:
    n = 12
    return ProjectModel(
        header=ProjectHeader(duration_months=n),
        settings=ProjectSettings(profit_tax_rate=Decimal("0.20")),
        operating_plan=OperatingPlan(
            products=[Product(id="p", name="Продукт")],
            # выручки нет в 1-м полугодии, издержки есть → дефицит
            sales=[SalesLine(product_id="p", volume=[Decimal(0)] * 6 + [Decimal(100)] * 6,
                             price=[Decimal(1000)] * n)],
            direct_costs=[DirectCostLine(name="м", kind=DirectCostKind.MATERIALS,
                                         amount=[Decimal(20000)] * n)],
            fixed_costs=[FixedCostLine(name="ф", function=CostFunction.ADMIN,
                                       amount=[Decimal(30000)] * n)],
        ),
        financing=Financing(auto_financing=AutoFinancing(
            enabled=auto, annual_rate=Decimal("0.18"), min_balance=Decimal(min_balance))),
    )


def test_without_auto_financing_cash_goes_negative():
    r = run(_deficit_project(auto=False))
    assert any(r.cashflow["C29"][t] < 0 for t in range(r.n))


def test_auto_financing_keeps_cash_above_min():
    r = run(_deficit_project(auto=True, min_balance="1000"))
    for t in range(r.n):
        assert r.cashflow["C29"][t] >= Decimal("1000") - EPS


def test_auto_financing_invariant_holds():
    r = run(_deficit_project(auto=True))
    for t in range(r.n):
        assert abs(r.balance["B20"][t] - r.balance["B34"][t]) <= EPS
        assert abs(r.balance["B1"][t] - r.cashflow["C29"][t]) <= EPS


def test_auto_financing_generates_interest_and_short_term_debt():
    r = run(_deficit_project(auto=True))
    assert any(v > 0 for v in r.income["I18"])    # проценты по кредиту
    assert any(v > 0 for v in r.balance["B22"])   # краткосрочный долг (кредитная линия)


def test_auto_financing_converges_no_warning():
    r = run(_deficit_project(auto=True))
    assert not any("не сошёлся" in w for w in r.warnings)
