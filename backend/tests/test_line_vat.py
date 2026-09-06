"""Пер-строчная ставка НДС (SalesLine.vat_rate): льготные категории в одном проекте.

Числа выверены вручную; инвариант B20=B34 обязан сходиться.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Company,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.money import quantize as q

D = Decimal


def _model(sales):
    return ProjectModel(
        header=ProjectHeader(name="lv", start_date=date(2026, 1, 1), duration_months=1),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0.20")),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id=s.product_id, name=s.product_id) for s in sales], sales=sales),
    )


def test_per_line_vat_rates():
    """Хлеб 10% + техника 20% (глобальная): деньги с разным НДС, к уплате — сумма."""
    sales = [
        SalesLine(product_id="bread", volume=[D(10)], price=[D(100)], vat_rate=D("0.10")),
        SalesLine(product_id="tech", volume=[D(10)], price=[D(100)]),   # None → глобальная 20%
    ]
    r = run(_model(sales))
    assert q(r.income["I1"][0]) == D("2000.00")       # нетто-выручка без НДС
    assert q(r.cashflow["C1"][0]) == D("2300.00")     # 1100 (10%) + 1200 (20%)
    assert q(r.cashflow["C12"][0]) == D("300.00")     # НДС к уплате: 100 + 200
    assert [q(v) for v in r.balance["B20"]] == [q(v) for v in r.balance["B34"]]


def test_zero_line_vat_override():
    """Ставка строки 0 перекрывает глобальную (экспортоподобная льгота без валюты)."""
    sales = [SalesLine(product_id="p", volume=[D(10)], price=[D(100)], vat_rate=D("0"))]
    r = run(_model(sales))
    assert q(r.cashflow["C1"][0]) == D("1000.00")     # денег ровно нетто
    assert all(v == 0 for v in r.cashflow["C12"])     # НДС к уплате нет
