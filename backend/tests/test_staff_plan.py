"""План персонала (SPEC §8): штатные позиции → затраты на персонал (I13–I15) + взносы.

Числа выверены вручную; инвариант B20=B34 обязан сходиться.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Company,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    StaffPosition,
    StartingBalance,
)
from calc_core.models.common import CostFunction
from calc_core.money import quantize as q

D = Decimal


def _balanced(r) -> bool:
    return [q(v) for v in r.balance["B20"]] == [q(v) for v in r.balance["B34"]]


def _model(n, staff, contrib="0"):
    return ProjectModel(
        header=ProjectHeader(name="st", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0"),
                                 payroll_contribution_rate=D(contrib)),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(staff=staff),
    )


def test_staff_position_expands_to_salary_cost():
    """2 инженера × 100 ₽/мес на месяцы [0, 2): I13 = 200, 200, 0; деньги в C6."""
    n = 3
    pos = StaffPosition(name="Инженер", monthly_salary=D(100), headcount=D(2),
                        start_month=0, end_month=2)
    r = run(_model(n, [pos]))
    assert [q(v) for v in r.income["I13"]] == [D("200.00"), D("200.00"), D("0.00")]
    assert [q(v) for v in r.cashflow["C6"]] == [D("200.00"), D("200.00"), D("0.00")]
    assert _balanced(r)


def test_staff_contributions_load_payroll():
    """Взносы 30%: загруженная стоимость 100×1.3 = 130 (та же машинерия, что суммовые)."""
    n = 1
    pos = StaffPosition(name="Менеджер", monthly_salary=D(100))
    r = run(_model(n, [pos], contrib="0.30"))
    assert q(r.income["I13"][0]) == D("130.00")
    assert q(r.cashflow["C6"][0]) == D("130.00")
    assert _balanced(r)


def test_staff_function_routes_to_group():
    """Функция позиции разносит начисление: производство → I14, маркетинг → I15."""
    n = 1
    prod = StaffPosition(name="Рабочий", monthly_salary=D(80),
                         function=CostFunction.STAFF_PRODUCTION)
    mkt = StaffPosition(name="SMM", monthly_salary=D(50),
                        function=CostFunction.STAFF_MARKETING)
    r = run(_model(n, [prod, mkt]))
    assert q(r.income["I14"][0]) == D("80.00")
    assert q(r.income["I15"][0]) == D("50.00")
    assert all(v == 0 for v in r.income["I13"])
    assert _balanced(r)


def test_staff_open_ended_and_delay():
    """end_month=None — до конца горизонта; задержка выплаты создаёт кредиторку B23."""
    n = 3
    pos = StaffPosition(name="Директор", monthly_salary=D(100), start_month=1,
                        payment_delay_months=1)
    r = run(_model(n, [pos]))
    assert [q(v) for v in r.income["I13"]] == [D("0.00"), D("100.00"), D("100.00")]
    assert [q(v) for v in r.cashflow["C6"]] == [D("0.00"), D("0.00"), D("100.00")]
    assert [q(v) for v in r.balance["B23"]] == [D("0.00"), D("100.00"), D("100.00")]
    assert _balanced(r)


def test_empty_staff_is_inert():
    r = run(_model(2, []))
    assert all(v == 0 for v in r.income["I13"])
    assert all(v == 0 for v in r.cashflow["C6"])
    assert _balanced(r)
