"""Группировка ОС (SPEC §9): разнос остаточной стоимости по B12/B13/B14.

- **Земля** (B12) не амортизируется и вне базы налога на имущество;
- **здания** (B13) и **оборудование** (B14) амортизируются и облагаются налогом;
- стартовая остаточная стоимость без разбивки относится к оборудованию (B14).
Числа выведены вручную; баланс B20=B34 сходится.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Asset,
    AssetCategory,
    Company,
    InvestmentPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    StartingBalance,
)

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def _model(n, assets, *, property_tax="0", start=StartingBalance()):
    return ProjectModel(
        header=ProjectHeader(name="cat", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D(property_tax), vat_rate=D("0")),
        company=Company(starting_balance=start),
        investment_plan=InvestmentPlan(assets=assets),
    )


def test_land_not_depreciated_and_outside_property_tax():
    """Земля: остаётся по стоимости в B12, без амортизации и без налога на имущество."""
    n = 3
    land = Asset(name="земля", cost=D(100000), purchase_month=0, life_months=12,
                 category=AssetCategory.LAND)
    r = run(_model(n, [land], property_tax="0.12"))   # 1% в месяц — если бы облагалась
    assert [quantize(v) for v in r.balance["B12"]] == [D("100000.00")] * 3
    assert all(v == 0 for v in r.balance["B13"]) and all(v == 0 for v in r.balance["B14"])
    assert all(v == 0 for v in r.income["I17"])       # амортизации нет
    assert all(v == 0 for v in r.income["I9"])        # земля вне базы налога на имущество
    assert _balanced(r)


def test_buildings_depreciate_into_b13():
    """Здание 12000/12 мес.: амортизация 1000/мес.; остаточная стоимость в B13."""
    n = 2
    bld = Asset(name="здание", cost=D(12000), purchase_month=0, life_months=12,
                category=AssetCategory.BUILDINGS)
    r = run(_model(n, [bld], property_tax="0.024"))   # 0.2% в месяц
    assert [quantize(v) for v in r.balance["B13"]] == [D("11000.00"), D("10000.00")]
    assert [quantize(v) for v in r.income["I17"]] == [D("1000.00"), D("1000.00")]
    # налог на имущество от остаточной стоимости здания (на конец периода)
    assert [quantize(v) for v in r.income["I9"]] == [D("22.00"), D("20.00")]
    assert all(v == 0 for v in r.balance["B12"]) and all(v == 0 for v in r.balance["B14"])
    assert _balanced(r)


def test_equipment_default_and_starting_residual_in_b14():
    """По умолчанию — оборудование (B14); стартовая остаточная стоимость тоже в B14."""
    n = 2
    eq = Asset(name="станок", cost=D(12000), purchase_month=0, life_months=12)  # default EQUIPMENT
    start = StartingBalance(fixed_assets_net=D(5000), paid_in_capital=D(5000))
    r = run(_model(n, [eq], start=start))
    assert [quantize(v) for v in r.balance["B14"]] == [D("16000.00"), D("15000.00")]
    assert all(v == 0 for v in r.balance["B12"]) and all(v == 0 for v in r.balance["B13"])
    assert _balanced(r)


def test_property_tax_base_excludes_only_land():
    """Земля + оборудование: налог на имущество — только с оборудования."""
    n = 1
    land = Asset(name="земля", cost=D(100000), category=AssetCategory.LAND)
    eq = Asset(name="станок", cost=D(12000), life_months=12)  # дооценка 1000 за 1 мес → 11000
    r = run(_model(n, [land, eq], property_tax="0.12"))       # 1% в месяц
    assert [quantize(v) for v in r.balance["B12"]] == [D("100000.00")]
    assert [quantize(v) for v in r.balance["B14"]] == [D("11000.00")]
    assert [quantize(v) for v in r.income["I9"]] == [D("110.00")]   # 0.01 × 11000 (без земли)
    assert _balanced(r)
