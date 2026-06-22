"""Налог с продаж (I3): оборотный налог на выручку (SPEC §11, §12)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def _model(profit_tax: str) -> ProjectModel:
    return ProjectModel(
        header=ProjectHeader(name="st", start_date=date(2026, 1, 1), duration_months=1),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D(profit_tax),
                                 property_tax_rate=D("0"), vat_rate=D("0"), sales_tax_rate=D("0.05")),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Товар")],
            sales=[SalesLine(product_id="p1", volume=[D(10)], price=[D(100)])],
        ),
    )


def test_sales_tax_reduces_net_sales_and_paid_in_cash():
    """Ставка 5% от выручки 1000 → I3=50, чистый объём 950; уплачивается (C12)."""
    r = run(_model("0"))
    assert r.income["I1"] == [D(1000)]
    assert r.income["I3"] == [D(50)]
    assert r.income["I4"] == [D(950)]    # I1 − I2 − I3
    assert r.income["I28"] == [D(950)]
    assert r.cashflow["C12"] == [D(50)]  # налог с продаж в строке «Налоги»
    assert _balanced(r)


def test_sales_tax_is_deductible_for_profit_tax():
    """Налог с продаж уменьшает налогооблагаемую прибыль: налог на прибыль с 950, не с 1000."""
    r = run(_model("0.20"))
    assert r.income["I3"] == [D(50)]
    assert r.income["I27"] == [D(190)]   # 20% от 950
    assert r.income["I28"] == [D(760)]   # 950 − 190
    assert r.cashflow["C12"] == [D(240)]  # 50 (с продаж) + 190 (на прибыль)
    assert _balanced(r)
