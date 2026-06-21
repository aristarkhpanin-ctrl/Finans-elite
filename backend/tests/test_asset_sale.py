"""Продажа основных средств (SPEC §9): C16, выбытие остаточной стоимости, фин. результат."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Asset,
    EquityInjection,
    Financing,
    InvestmentPlan,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
)

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def _sale_model(sale_price: Decimal) -> ProjectModel:
    """Станок 1200 (срок 12 → 100/мес), куплен в t0 за счёт капитала, продан в t2."""
    n = 3
    return ProjectModel(
        header=ProjectHeader(name="sale", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        investment_plan=InvestmentPlan(assets=[Asset(
            name="Станок", cost=D(1200), purchase_month=0, life_months=12,
            sale_month=2, sale_price=sale_price)]),
        financing=Financing(equity=[EquityInjection(amount=D(1200), month=0)],
                            common_shares=D(100)),
        operating_plan=OperatingPlan(),
    )


def test_asset_sale_with_gain():
    """Продажа за 1100 при остаточной 1000 → прибыль 100; амортизация прекращается."""
    r = run(_sale_model(D(1100)))
    assert r.income["I17"] == [D(100), D(100), D(0)]      # амортизация останавливается в t2
    assert r.balance["B14"] == [D(1100), D(1000), D(0)]   # остаточная списана при продаже
    assert r.cashflow["C16"] == [D(0), D(0), D(1100)]     # поступления от реализации
    assert r.income["I20"] == [D(0), D(0), D(100)]        # прибыль = 1100 − 1000
    assert r.income["I21"] == [D(0), D(0), D(0)]
    assert _balanced(r)


def test_asset_sale_with_loss():
    """Продажа за 800 при остаточной 1000 → убыток 200 (I21)."""
    r = run(_sale_model(D(800)))
    assert r.income["I21"] == [D(0), D(0), D(200)]        # убыток = 1000 − 800
    assert r.income["I20"] == [D(0), D(0), D(0)]
    assert r.cashflow["C16"] == [D(0), D(0), D(800)]
    assert _balanced(r)
