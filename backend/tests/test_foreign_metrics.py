"""Показатели во второй валюте (SPEC §17, gap 1.4).

Ставка дисконтирования по валюте (`discount_rate_annual_foreign`) включает дубль-блок
показателей: чистый поток до финансирования пересчитывается во вторую валюту по курсу
(`Environment.fx_rate`) и дисконтируется своей ставкой. Ставка = 0 → блока нет (инертно).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.metrics import annual_to_monthly, npv
from calc_core.models import (
    Asset,
    Company,
    Environment,
    Financing,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.money import quantize

D = Decimal


def _model(fx_open: str, fx_rate, foreign_rate: str) -> ProjectModel:
    """Актив (отток C20) + продажи (приток C13); вторая валюта задана курсом."""
    n = len(fx_rate)
    return ProjectModel(
        header=ProjectHeader(name="fc", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(
            discount_rate_annual=D("0.15"),
            discount_rate_annual_foreign=D(foreign_rate),
            profit_tax_rate=D("0"), property_tax_rate=D("0"), vat_rate=D("0"),
        ),
        environment=Environment(fx_open=D(fx_open), fx_rate=[D(x) for x in fx_rate]),
        company=Company(starting_balance=StartingBalance(
            cash=D(100000), fixed_assets_net=D(0), paid_in_capital=D(100000))),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="A")],
            sales=[SalesLine(product_id="p1", volume=[D(50)] * n, price=[D(1000)] * n)],
        ),
        financing=Financing(common_shares=D(100)),
    )


def _model_with_asset(fx_open: str, fx_rate, foreign_rate: str) -> ProjectModel:
    m = _model(fx_open, fx_rate, foreign_rate)
    m.investment_plan.assets = [
        Asset(name="Станок", cost=D(60000), purchase_month=0, life_months=len(fx_rate)),
    ]
    return m


def _net_flow(r):
    return [a + b for a, b in zip(r.cashflow["C13"], r.cashflow["C20"], strict=True)]


def test_foreign_metrics_absent_when_rate_zero():
    """Ставка по валюте не задана → блок показателей во второй валюте отсутствует."""
    r = run(_model_with_asset("60", [D(60) + D(i) for i in range(12)], "0"))
    assert r.metrics_foreign is None


def test_foreign_metrics_present_and_matches_converted_flow():
    """Ставка задана → NPV во второй валюте = NPV пересчитанного по курсу потока."""
    fx = [D(60) + D(i) for i in range(12)]
    m = _model_with_asset("60", fx, "0.10")
    r = run(m)
    assert r.metrics_foreign is not None

    net = _net_flow(r)
    foreign_flow = [net[t] / fx[t] for t in range(12)]
    expected = npv(foreign_flow, annual_to_monthly(D("0.10")))
    assert quantize(r.metrics_foreign.npv) == quantize(expected)
    # Основной блок считается в рублях по своей ставке — не совпадает с валютным.
    assert quantize(r.metrics.npv) != quantize(r.metrics_foreign.npv)


def test_foreign_equals_main_when_fx_one_and_same_rate():
    """Курс 1:1 и та же ставка → показатели во второй валюте совпадают с основными."""
    m = _model_with_asset("1", [D(1)] * 12, "0.15")
    r = run(m)
    assert r.metrics_foreign is not None
    assert quantize(r.metrics_foreign.npv) == quantize(r.metrics.npv)
    assert r.metrics_foreign.irr_annual == r.metrics.irr_annual
    assert r.metrics_foreign.pb_months == r.metrics.pb_months


def test_invariant_holds_with_foreign_rate():
    """Дубль-блок — только показатели; отчёты и баланс не меняются."""
    fx = [D(60) + D(i) for i in range(12)]
    a = run(_model_with_asset("60", fx, "0"))
    b = run(_model_with_asset("60", fx, "0.10"))
    # Отчёты идентичны при любой ставке по валюте (показатель — производная от потока).
    for code in a.cashflow.order:
        assert [quantize(v) for v in a.cashflow[code]] == [quantize(v) for v in b.cashflow[code]]
    assert [quantize(v) for v in b.balance["B20"]] == [quantize(v) for v in b.balance["B34"]]
