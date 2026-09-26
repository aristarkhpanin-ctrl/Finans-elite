"""Тесты доинвестирования в актив (SPEC §9, gap 1.6, AD0).

Доп. вложение капитализируется (C14), амортизируется от остаточного срока, растит
остаточную стоимость. Актив без доинвестиций считается как прежде (golden без дрейфа).
"""
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    AdditionalInvestment,
    Asset,
    Financing,
    InvestmentPlan,
    OperatingPlan,
    Product,
    ProjectModel,
    SalesLine,
)
from calc_core.models.common import AssetCategory
from calc_core.money import almost_equal


def _model(assets, n=12) -> ProjectModel:
    model = ProjectModel()
    model.header.duration_months = n
    model.settings.vat_rate = Decimal("0.20")
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[SalesLine(product_id="p1", volume=[Decimal(30)] * n, price=[Decimal(1000)] * n)],
    )
    model.investment_plan = InvestmentPlan(assets=assets)
    model.financing = Financing()
    return model


def test_no_additional_matches_plain_asset():
    """Пустой список доинвестиций → активы считаются в точности как прежде."""
    a1 = Asset(name="Станок", cost=Decimal(120_000), purchase_month=0, life_months=12)
    a2 = Asset(name="Станок", cost=Decimal(120_000), purchase_month=0, life_months=12,
               additional_investments=[])
    r1, r2 = run(_model([a1])), run(_model([a2]))
    assert r1.balance["B14"] == r2.balance["B14"]
    assert r1.income["I17"] == r2.income["I17"]
    assert r1.cashflow["C14"] == r2.cashflow["C14"]


def test_additional_raises_capex_depreciation_nbv():
    """Доп. вложение растит C14 (с НДС), амортизацию и остаточную стоимость."""
    base = _model([Asset(name="Станок", cost=Decimal(120_000), purchase_month=0, life_months=12)])
    upgraded = _model([Asset(
        name="Станок", cost=Decimal(120_000), purchase_month=0, life_months=12,
        additional_investments=[AdditionalInvestment(month=6, amount=Decimal(60_000))])])
    r0, r1 = run(base), run(upgraded)
    # C14 в месяце 6 вырос на сумму с НДС
    assert r1.cashflow["C14"][6] - r0.cashflow["C14"][6] == Decimal(60_000) * Decimal("1.20")
    # амортизация после доинвестиции выше
    assert sum(r1.income["I17"], Decimal(0)) > sum(r0.income["I17"], Decimal(0))
    # остаточная стоимость оборудования в середине срока выше (доп. вложение ещё не списано)
    assert r1.balance["B14"][8] > r0.balance["B14"][8]


def test_additional_depreciates_over_remaining_life():
    """Вложение 60k в мес.6 при сроке до мес.12 → 6 мес. остатка → 10k/мес доп. амортизации."""
    base = _model([Asset(name="Ст", cost=Decimal(120_000), purchase_month=0, life_months=12)])
    up = _model([Asset(name="Ст", cost=Decimal(120_000), purchase_month=0, life_months=12,
                       additional_investments=[AdditionalInvestment(month=6, amount=Decimal(60_000))])])
    r0, r1 = run(base), run(up)
    # с мес.6 амортизация выросла ровно на 60000/6 = 10000/мес
    for t in range(6, 12):
        assert almost_equal(r1.income["I17"][t] - r0.income["I17"][t], Decimal(10_000))
    # к концу срока доп. вложение полностью самортизировано → B14 сравнивается с базой
    assert almost_equal(r1.balance["B14"][11], r0.balance["B14"][11])


def test_land_additional_not_depreciated():
    """Земля: доп. вложение капитализируется, но не амортизируется (растит B12)."""
    m = _model([Asset(name="Участок", cost=Decimal(500_000), purchase_month=0, life_months=12,
                      category=AssetCategory.LAND,
                      additional_investments=[AdditionalInvestment(month=3, amount=Decimal(100_000))])])
    r = run(m)
    assert all(v == 0 for v in r.income["I17"])              # амортизации нет
    assert r.balance["B12"][-1] == Decimal(600_000)          # земля + доинвестиция

    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))


def test_sale_after_additional_investment():
    """Продажа после доинвестиции: остаточная включает недоамортизированное вложение."""
    m = _model([Asset(
        name="Ст", cost=Decimal(120_000), purchase_month=0, life_months=24,
        additional_investments=[AdditionalInvestment(month=6, amount=Decimal(60_000))],
        sale_month=12, sale_price=Decimal(100_000))], n=18)
    r = run(m)
    assert r.cashflow["C16"][12] == Decimal(100_000)        # поступление от продажи
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))
    # после продажи остаточная стоимость обнулилась
    assert r.balance["B14"][13] == Decimal(0)


def test_invariant_with_additional():
    m = _model([Asset(name="Ст", cost=Decimal(200_000), purchase_month=1, life_months=10,
                      additional_investments=[
                          AdditionalInvestment(month=3, amount=Decimal(50_000)),
                          AdditionalInvestment(month=7, amount=Decimal(30_000))])])
    r = run(m)
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))
