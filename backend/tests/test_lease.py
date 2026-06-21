"""Операционный лизинг (SPEC §10): платёж = издержка (I21) + отток (C25)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Financing,
    Lease,
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


def test_operating_lease_expense_and_cash():
    """Лизинг 500/мес ×2: издержка в I21 и отток в C25; баланс сходится."""
    n = 2
    m = ProjectModel(
        header=ProjectHeader(name="lease", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        financing=Financing(leases=[Lease(name="Авто", monthly_payment=D(500),
                                          start_month=0, term_months=2)], common_shares=D(100)),
        operating_plan=OperatingPlan(),
    )
    r = run(m)
    assert r.income["I21"] == [D(500), D(500)]
    assert r.cashflow["C25"] == [D(500), D(500)]
    assert r.balance["B1"] == [D(-500), D(-1000)]
    assert _balanced(r)


def test_lease_is_deductible():
    """Лизинговый платёж уменьшает налогооблагаемую прибыль (вычитаемая издержка)."""
    m = ProjectModel(
        header=ProjectHeader(duration_months=1),
        settings=ProjectSettings(profit_tax_rate=D("0.20"), vat_rate=D("0")),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(50)], price=[D(100)])],
        ),
        financing=Financing(leases=[Lease(name="Авто", monthly_payment=D(500), term_months=1)]),
    )
    r = run(m)
    assert r.income["I23"] == [D(4500)]    # 5000 − 500
    assert r.income["I27"] == [D(900)]     # 20% от 4500 (а не от 5000)
    assert _balanced(r)
