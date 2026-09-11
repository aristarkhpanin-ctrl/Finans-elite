"""Тесты детализации стартовых ОС (SPEC §9/§14, gap 1.7, SO0).

Пред-существующий актив (purchase_month<0) доамортизируется с t=0, виден в B14,
может быть продан. Остаточная стоимость на t=−1 сворачивается в стартовый баланс.
Без пред-существующих ОС — инертно (golden без дрейфа).
"""
from decimal import Decimal

import pytest

from calc_core import run
from calc_core.engine import ModelError
from calc_core.engine.pipeline import _preexisting_net_open
from calc_core.models import (
    Asset,
    Company,
    InvestmentPlan,
    OperatingPlan,
    Product,
    ProjectModel,
    SalesLine,
)
from calc_core.models.common import AssetCategory
from calc_core.models.company import StartingBalance
from calc_core.money import almost_equal

D = Decimal


def _model(assets, retained="0", fixed_net="0", n=12) -> ProjectModel:
    model = ProjectModel()
    model.header.duration_months = n
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[SalesLine(product_id="p1", volume=[D(10)] * n, price=[D(1000)] * n)])
    model.investment_plan = InvestmentPlan(assets=assets)
    model.company = Company(starting_balance=StartingBalance(
        fixed_assets_net=D(fixed_net), retained_earnings=D(retained)))
    return model


def test_preexisting_net_open_computation():
    """Остаточная на t=−1: cost − ставка·min(−month, life); земля — по стоимости."""
    m = _model([
        Asset(name="Станок", cost=D(120_000), purchase_month=-6, life_months=12),   # 60000
        Asset(name="Земля", cost=D(500_000), purchase_month=-3, life_months=12,      # 500000
              category=AssetCategory.LAND),
    ])
    assert _preexisting_net_open(m) == D(560_000)


def test_preexisting_asset_depreciates_and_balances():
    """Пред-существующий актив амортизируется с t=0, инвариант держится."""
    m = _model([Asset(name="Старый станок", cost=D(120_000), purchase_month=-6, life_months=12)],
               retained="60000")   # нетто на t=−1 = 60000 → балансируем прибылью
    r = run(m)
    assert r.balance["B14"][0] == D(50_000)              # 60000 − амортизация месяца 0
    assert r.balance["B14"][5] == D(0)                   # доамортизирован к месяцу 5
    assert all(almost_equal(r.income["I17"][t], D(10_000)) for t in range(6))
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))


def test_starting_balance_must_balance_with_preexisting():
    """Без балансировки капиталом пред-существующий актив → ModelError."""
    m = _model([Asset(name="Ст", cost=D(120_000), purchase_month=-6, life_months=12)],
               retained="0")       # нетто 60000 не сбалансирован → ошибка
    with pytest.raises(ModelError, match="Стартовый баланс не сходится"):
        run(m)


def test_preexisting_asset_sale():
    """Пред-существующий актив можно продать: поступление C16, инвариант держится."""
    m = _model([Asset(name="Старый", cost=D(240_000), purchase_month=-12, life_months=24,
                      sale_month=6, sale_price=D(80_000))],
               retained="120000", n=12)   # нетто на t=−1 = 240000 − 10000·12 = 120000
    r = run(m)
    assert r.cashflow["C16"][6] == D(80_000)
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))


def test_land_preexisting_not_depreciated():
    """Пред-существующая земля: нетто = стоимость, не амортизируется."""
    m = _model([Asset(name="Участок", cost=D(300_000), purchase_month=-24, life_months=12,
                      category=AssetCategory.LAND)],
               retained="300000")
    r = run(m)
    assert all(v == 0 for v in r.income["I17"])          # амортизации нет
    assert r.balance["B12"][0] == D(300_000)             # земля по стоимости
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))


def test_no_preexisting_inert():
    """Все активы с purchase_month≥0 → поправка 0 (инертность)."""
    m = _model([Asset(name="Новый", cost=D(100_000), purchase_month=0, life_months=12)])
    assert _preexisting_net_open(m) == D(0)
    r = run(m)                                            # балансируется как обычно (capex из кассы)
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))
