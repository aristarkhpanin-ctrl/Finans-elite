"""Прочие поступления/выплаты (SPEC §12/§13): I20/C10 и I21|I24/C11, начисление = оплата.

Числа выверены вручную; инвариант B20=B34 обязан сходиться.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Company,
    OperatingPlan,
    OtherFlow,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    StartingBalance,
)
from calc_core.money import quantize as q

D = Decimal


def _balanced(r) -> bool:
    return [q(v) for v in r.balance["B20"]] == [q(v) for v in r.balance["B34"]]


def _model(n, income=None, expenses=None, tax="0"):
    return ProjectModel(
        header=ProjectHeader(name="of", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D(tax),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(other_income=income or [], other_expenses=expenses or []),
    )


def test_other_income_flows_to_i20_and_c10():
    n = 2
    r = run(_model(n, income=[OtherFlow(name="Субсидия", amount=[D(500), D(0)])]))
    assert [q(v) for v in r.income["I20"]] == [D("500.00"), D("0.00")]
    assert [q(v) for v in r.cashflow["C10"]] == [D("500.00"), D("0.00")]
    assert [q(v) for v in r.balance["B1"]] == [D("500.00"), D("500.00")]   # деньги пришли
    assert _balanced(r)


def test_other_expense_deductible():
    """Вычитаемая выплата: I21 уменьшает налоговую базу (налог 20%)."""
    n = 1
    r = run(_model(n, income=[OtherFlow(name="Доход", amount=[D(1000)])],
                   expenses=[OtherFlow(name="Штраф банка", amount=[D(400)])], tax="0.20"))
    assert q(r.income["I21"][0]) == D("400.00")
    assert q(r.cashflow["C11"][0]) == D("400.00")
    assert q(r.income["I27"][0]) == D("120.00")     # налог: (1000−400)×20%
    assert q(r.income["I28"][0]) == D("480.00")     # чистая прибыль
    assert _balanced(r)


def test_other_expense_from_profit_not_deductible():
    """Выплата «из прибыли» (I24): налоговую базу не уменьшает, чистую прибыль — да."""
    n = 1
    r = run(_model(n, income=[OtherFlow(name="Доход", amount=[D(1000)])],
                   expenses=[OtherFlow(name="Благотворительность", amount=[D(400)],
                                       from_profit=True)], tax="0.20"))
    assert q(r.income["I24"][0]) == D("400.00")
    assert all(v == 0 for v in r.income["I21"])
    assert q(r.income["I27"][0]) == D("200.00")     # налог с полной базы 1000×20%
    assert q(r.income["I28"][0]) == D("400.00")     # 1000 − 400 (I24) − 200 (налог)
    assert q(r.cashflow["C11"][0]) == D("400.00")   # деньги ушли в любом случае
    assert _balanced(r)


def test_no_other_flows_is_inert():
    r = run(_model(2))
    assert all(v == 0 for v in r.income["I20"])
    assert all(v == 0 for v in r.cashflow["C10"])
    assert all(v == 0 for v in r.cashflow["C11"])
    assert _balanced(r)
