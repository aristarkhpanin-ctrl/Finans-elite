"""Тесты НМА как класса актива (SPEC §9, gap 1.8, IA0).

НМА (AssetCategory.INTANGIBLE) амортизируется (I17), остаточная стоимость → B16
(Другие активы), вне базы налога на имущество. Без НМА B16=0 → golden без дрейфа.
"""
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Asset,
    InvestmentPlan,
    OperatingPlan,
    Product,
    ProjectModel,
    SalesLine,
)
from calc_core.models.common import AssetCategory
from calc_core.money import almost_equal


def _model(assets, n=12, property_rate="0") -> ProjectModel:
    model = ProjectModel()
    model.header.duration_months = n
    model.settings.vat_rate = Decimal("0.20")
    model.settings.property_tax_rate = Decimal(property_rate)
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[SalesLine(product_id="p1", volume=[Decimal(50)] * n, price=[Decimal(1000)] * n)],
    )
    model.investment_plan = InvestmentPlan(assets=assets)
    return model


def test_intangible_amortizes_and_nbv_in_b16():
    """НМА амортизируется (I17) и остаточная стоимость учитывается в B16."""
    nma = Asset(name="Лицензия ПО", cost=Decimal(120_000), purchase_month=0, life_months=12,
                category=AssetCategory.INTANGIBLE)
    r = run(_model([nma]))
    # амортизация линейная: 120000/12 = 10000/мес
    assert all(almost_equal(r.income["I17"][t], Decimal(10_000)) for t in range(12))
    # остаточная стоимость в B16: 120000 − 10000·(t+1)
    for t in range(12):
        assert almost_equal(r.balance["B16"][t], Decimal(120_000) - Decimal(10_000) * (t + 1))
    # НМА не попадает в остаточную стоимость ОС по группам (B12/B13/B14 = 0)
    assert all(v == 0 for v in r.balance["B14"])
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))


def test_intangible_not_in_property_tax():
    """НМА (B16) вне базы налога на имущество (база — B13+B14)."""
    nma = Asset(name="Патент", cost=Decimal(240_000), purchase_month=0, life_months=24,
                category=AssetCategory.INTANGIBLE)
    equip = Asset(name="Станок", cost=Decimal(240_000), purchase_month=0, life_months=24,
                  category=AssetCategory.EQUIPMENT)
    r_nma = run(_model([nma], property_rate="0.02"))
    r_eq = run(_model([equip], property_rate="0.02"))
    # у оборудования налог на имущество есть, у НМА — нет
    assert sum(r_nma.income["I9"], Decimal(0)) == 0
    assert sum(r_eq.income["I9"], Decimal(0)) > 0


def test_intangible_capex_with_vat():
    """Приобретение НМА — денежный отток в C14 с НДС (как любой актив)."""
    nma = Asset(name="CRM", cost=Decimal(100_000), purchase_month=1, life_months=10,
                category=AssetCategory.INTANGIBLE)
    r = run(_model([nma]))
    assert almost_equal(r.cashflow["C14"][1], Decimal(100_000) * Decimal("1.20"))


def test_intangible_sale():
    """Продажа НМА: поступление C16, остаточная списывается, инвариант держится."""
    nma = Asset(name="Бренд", cost=Decimal(120_000), purchase_month=0, life_months=24,
                category=AssetCategory.INTANGIBLE, sale_month=12, sale_price=Decimal(70_000))
    r = run(_model([nma], n=18))
    assert r.cashflow["C16"][12] == Decimal(70_000)
    assert r.balance["B16"][13] == Decimal(0)               # после продажи НМА списан
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))


def test_no_intangible_keeps_b16_zero():
    """Без НМА B16 остаётся нулём (golden-инертность категории)."""
    equip = Asset(name="Станок", cost=Decimal(100_000), purchase_month=0, life_months=12)
    r = run(_model([equip]))
    assert all(v == 0 for v in r.balance["B16"])
