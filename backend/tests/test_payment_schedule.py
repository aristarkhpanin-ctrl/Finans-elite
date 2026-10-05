"""Сложные схемы оплаты продаж (SPEC §5): график долей со сдвигами (PaymentTerms.schedule).

Числа выверены вручную; инвариант B20=B34 обязан сходиться.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Company,
    OperatingPlan,
    PaymentPart,
    PaymentTerms,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.money import quantize as q

D = Decimal


def _balanced(r) -> bool:
    return [q(v) for v in r.balance["B20"]] == [q(v) for v in r.balance["B34"]]


def _model(n, payment, volume, price=100):
    sales = SalesLine(product_id="p1", volume=[D(v) for v in volume],
                      price=[D(price)] * n, payment=payment)
    return ProjectModel(
        header=ProjectHeader(name="ps", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(products=[Product(id="p1", name="P")], sales=[sales]),
    )


def test_schedule_with_advance_and_installments():
    """Отгрузка 1000 в мес. 1: 30% аванс за 1 мес, 50% при отгрузке, 20% через 2 мес."""
    n = 4
    pay = PaymentTerms(schedule=[
        PaymentPart(offset_months=-1, share=D("0.3")),
        PaymentPart(offset_months=0, share=D("0.5")),
        PaymentPart(offset_months=2, share=D("0.2")),
    ])
    r = run(_model(n, pay, [0, 10, 0, 0]))
    assert [q(v) for v in r.cashflow["C1"]] == [D("300.00"), D("500.00"), D("0.00"), D("200.00")]
    assert [q(v) for v in r.balance["B24"]] == [D("300.00"), D("0.00"), D("0.00"), D("0.00")]
    assert [q(v) for v in r.balance["B2"]] == [D("0.00"), D("200.00"), D("200.00"), D("0.00")]
    assert q(r.income["I1"][1]) == D("1000.00")           # начисление — в месяц отгрузки
    assert _balanced(r)


def test_schedule_remainder_balances_at_shipment():
    """Σ долей 0.6 → остаток 0.4 автоматически в месяце отгрузки (оплаты = выручке)."""
    n = 3
    pay = PaymentTerms(schedule=[PaymentPart(offset_months=1, share=D("0.6"))])
    r = run(_model(n, pay, [10, 0, 0]))
    assert [q(v) for v in r.cashflow["C1"]] == [D("400.00"), D("600.00"), D("0.00")]
    assert q(sum(r.cashflow["C1"])) == D("1000.00")
    assert _balanced(r)


def test_empty_schedule_equals_simple_terms():
    """Пустой schedule → простая схема; результаты идентичны байт-в-байт."""
    n = 4
    simple = PaymentTerms(prepayment_share=D("0.3"), advance_lead_months=1,
                          payment_delay_months=2)
    scheduled = PaymentTerms(schedule=[
        PaymentPart(offset_months=-1, share=D("0.3")),
        PaymentPart(offset_months=2, share=D("0.7")),
    ])
    r1 = run(_model(n, simple, [0, 10, 5, 0]))
    r2 = run(_model(n, scheduled, [0, 10, 5, 0]))
    for code in ("C1", "C29"):
        assert [q(v) for v in r1.cashflow[code]] == [q(v) for v in r2.cashflow[code]]
    for code in ("B2", "B24", "B20"):
        assert [q(v) for v in r1.balance[code]] == [q(v) for v in r2.balance[code]]
