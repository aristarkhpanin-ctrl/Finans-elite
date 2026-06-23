"""Оценка бизнеса (SPEC §20): чистые активы (B33) и модель Гордона."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.reports.valuation import BusinessValuation, compute_valuation
from calc_core.models import (
    Financing,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)

D = Decimal


def _project(discount: Decimal, growth: Decimal, *, dividends=None,
             multiple: Decimal = D("0"), liquidation: Decimal = D("0")) -> ProjectModel:
    """3 мес., продажи 1000/мес. по кассе, без затрат/налогов/инвестиций."""
    n = 3
    sales = SalesLine(product_id="p0", volume=[D(10)] * n, price=[D(100)] * n)
    return ProjectModel(
        header=ProjectHeader(name="val", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=discount, terminal_growth_rate=growth,
                                 valuation_earnings_multiple=multiple,
                                 liquidation_recovery_rate=liquidation,
                                 profit_tax_rate=D("0"), property_tax_rate=D("0"), vat_rate=D("0")),
        operating_plan=OperatingPlan(products=[Product(id="p0", name="p0")], sales=[sales]),
        financing=Financing(dividends=(dividends or [])),
    )


def test_net_assets_equals_closing_equity():
    """Чистые активы = собственный капитал на конец (B33): 3×1000 нераспределённой прибыли."""
    r = run(_project(D("0.15"), D("0")))
    assert quantize(r.valuation.net_assets) == D("3000.00")
    assert quantize(r.balance["B33"][r.n - 1]) == D("3000.00")


def test_gordon_no_growth():
    """Поток 1000/мес → 12000/год; V = 12000/(0.15−0) = 80000."""
    r = run(_project(D("0.15"), D("0")))
    assert quantize(r.valuation.gordon_value) == D("80000.00")


def test_gordon_with_growth():
    """g=0.05: V = 12000·1.05/(0.15−0.05) = 126000."""
    r = run(_project(D("0.15"), D("0.05")))
    assert quantize(r.valuation.gordon_value) == D("126000.00")


def test_gordon_none_when_rate_not_above_growth():
    """r ≤ g — формула Гордона неприменима (нет конечной капитализации)."""
    r = run(_project(D("0.10"), D("0.15")))
    assert r.valuation.gordon_value is None
    # чистые активы при этом считаются как обычно
    assert quantize(r.valuation.net_assets) == D("3000.00")


def test_dividend_discount_model():
    """DDM: дивиденды 500/мес → 6000/год; V = 6000/(0.15−0) = 40000."""
    r = run(_project(D("0.15"), D("0"), dividends=[D(500)] * 3))
    assert quantize(r.valuation.dividend_value) == D("40000.00")


def test_earnings_multiple():
    """Мультипликатор: годовая прибыль 12000 × 5 = 60000; без множителя — None."""
    r = run(_project(D("0.15"), D("0"), multiple=D("5")))
    assert quantize(r.valuation.earnings_multiple_value) == D("60000.00")
    assert run(_project(D("0.15"), D("0"))).valuation.earnings_multiple_value is None


def test_liquidation_value():
    """Ликвидация: 80% активов (3000) − обязательства (0) = 2400; без доли возврата — None."""
    r = run(_project(D("0.15"), D("0"), liquidation=D("0.8")))
    assert quantize(r.valuation.liquidation_value) == D("2400.00")
    assert run(_project(D("0.15"), D("0"))).valuation.liquidation_value is None


def test_empty_horizon_returns_default():
    """Защитный возврат для n ≤ 0 (балансы/потоки не читаются)."""
    assert compute_valuation(None, None, None, D("0.15"), D("0"), D("0"), D("0"), 0) == BusinessValuation()
