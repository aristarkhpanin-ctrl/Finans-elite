"""Депозиты/ЦБ (SPEC §10): вложение C8, доход C9, тело в B6."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Company,
    Deposit,
    Financing,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    StartingBalance,
)

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def test_deposit_placement_income_and_return():
    """Депозит 1000 на 2 мес из стартовых денег: тело в B6, доход в C9/I20, возврат в t2."""
    n = 3
    m = ProjectModel(
        header=ProjectHeader(name="dep", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        # 1000 стартовых денег, уравновешенных капиталом
        company=Company(starting_balance=StartingBalance(cash=D(1000), paid_in_capital=D(1000))),
        financing=Financing(deposits=[Deposit(name="Вклад", amount=D(1000), start_month=0,
                                              term_months=2, annual_rate=D("0.12"))],
                            common_shares=D(100)),
        operating_plan=OperatingPlan(),
    )
    r = run(m)
    rm = (D(1) + D("0.12")) ** (D(1) / D(12)) - D(1)
    income = quantize(D(1000) * rm)
    assert r.balance["B6"] == [D(1000), D(1000), D(0)]   # тело размещено t0,t1; возврат t2
    assert [quantize(v) for v in r.income["I20"]] == [income, income, D(0)]   # доход за t0,t1
    assert r.cashflow["C8"] == [D(1000), D(0), D(-1000)]  # размещение t0, возврат t2
    # деньги: t0 размещены (касса 0 + доход), тело вернулось в t2
    assert _balanced(r)


def test_no_deposit_keeps_b6_zero():
    m = ProjectModel(header=ProjectHeader(duration_months=2),
                     settings=ProjectSettings(profit_tax_rate=D("0"), vat_rate=D("0")))
    r = run(m)
    assert all(v == 0 for v in r.balance["B6"])
    assert all(v == 0 for v in r.cashflow["C8"])
