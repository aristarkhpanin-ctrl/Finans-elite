"""Тесты НДС (5.1c): Кэш-фло с НДС, ОПУ без НДС, зачёт и НДС-кредит (B7)."""
from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.engine.vat import settle_vat
from calc_core.models import (
    Asset,
    DirectCostLine,
    EquityInjection,
    Financing,
    InvestmentPlan,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)
from calc_core.models.common import DirectCostKind
from calc_core.series import cumulative, total


def test_settle_vat_basic():
    budget, credit = settle_vat([Decimal(100)] * 3, [Decimal(20)] * 3, 3)
    assert budget == [Decimal(80)] * 3
    assert credit == [Decimal(0)] * 3


def test_settle_vat_credit_carry_forward():
    # t0: входной 50 > исходящего 0 → к уплате 0, кредит 50; t1: исходящий 200 − кредит 50
    budget, credit = settle_vat([Decimal(0), Decimal(200)], [Decimal(50), Decimal(0)], 2)
    assert budget == [Decimal(0), Decimal(150)]
    assert credit == [Decimal(50), Decimal(0)]


def _vat_project(vat: str) -> ProjectModel:
    n = 6
    return ProjectModel(
        header=ProjectHeader(name="НДС", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(vat_rate=Decimal(vat), profit_tax_rate=Decimal("0.20")),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Товар")],
            sales=[SalesLine(product_id="p1", volume=[Decimal(0)] + [Decimal(10)] * 5,
                             price=[Decimal(1000)] * n)],
            direct_costs=[DirectCostLine(name="мат", kind=DirectCostKind.MATERIALS,
                                         amount=[Decimal(0)] + [Decimal(4000)] * 5)],
        ),
        investment_plan=InvestmentPlan(
            assets=[Asset(name="Линия", cost=Decimal(300000), purchase_month=0, life_months=60)]
        ),
        financing=Financing(equity=[EquityInjection(amount=Decimal(500000), month=0)]),
    )


def test_pl_net_of_vat_cashflow_gross():
    with_vat = run(_vat_project("0.20"))
    no_vat = run(_vat_project("0"))
    # ОПУ без НДС: выручка I1 не зависит от ставки НДС
    assert with_vat.income["I1"] == no_vat.income["I1"]
    # Кэш-фло с НДС: суммарные поступления от продаж больше ровно на 20%
    assert total(with_vat.cashflow["C1"]) == total(no_vat.cashflow["C1"]) * Decimal("1.2")


def test_vat_credit_appears_on_capex_then_used():
    r = run(_vat_project("0.20"))
    # в месяце 0 крупный capex (входной НДС), продаж нет → НДС-кредит в B7 > 0
    assert r.balance["B7"][0] > 0
    # кредит со временем расходуется (исходящий НДС от продаж) → к концу меньше
    assert r.balance["B7"][r.n - 1] < r.balance["B7"][0]


def test_vat_invariant_holds():
    r = run(_vat_project("0.20"))
    for t in range(r.n):
        assert abs(r.balance["B20"][t] - r.balance["B34"][t]) <= Decimal("0.01")


def test_vat_in_taxes_line():
    r = run(_vat_project("0.20"))
    # НДС к уплате входит в строку «Налоги» C12 — суммарно положителен
    assert total(r.cashflow["C12"]) > 0
