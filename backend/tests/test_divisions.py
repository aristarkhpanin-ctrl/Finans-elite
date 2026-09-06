"""Маржа по подразделениям (gap 4.5): свёртка маржи продуктов бизнес-единицы.

Аналитика поверх product_margins — суммирует продукты с рецептурой, отнесённые к
подразделению (`Product.division_id`). Без подразделений отчёт пуст (и вне снимка);
отчётные формы и golden-числа не затрагиваются.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    BomLine,
    Company,
    Division,
    Material,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.money import quantize as q

D = Decimal


def _model(n, products, sales, divisions=None, materials=None):
    return ProjectModel(
        header=ProjectHeader(name="div", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        company=Company(starting_balance=StartingBalance(), divisions=divisions or []),
        operating_plan=OperatingPlan(products=products, sales=sales, materials=materials or []),
    )


def test_division_margins_rollup():
    """Два продукта с рецептурой в одном подразделении → свёртка выручки/маржи; третий
    продукт в другом подразделении — отдельная строка."""
    n = 2
    mat = Material(id="m1", name="Сталь", unit_price=D(5))
    a = Product(id="a", name="A", division_id="d1",
                bom=[BomLine(material_id="m1", qty_per_unit=D(3))], piece_wage_per_unit=D(7))
    b = Product(id="b", name="B", division_id="d1", piece_wage_per_unit=D(2))
    c = Product(id="c", name="C", division_id="d2",
                bom=[BomLine(material_id="m1", qty_per_unit=D(1))])
    sales = [
        SalesLine(product_id="a", volume=[D(10)] * n, price=[D(100)] * n),
        SalesLine(product_id="b", volume=[D(5)] * n, price=[D(50)] * n),
        SalesLine(product_id="c", volume=[D(4)] * n, price=[D(80)] * n),
    ]
    divs = [Division(id="d1", name="Производство"), Division(id="d2", name="Экспорт")]
    r = run(_model(n, [a, b, c], sales, divisions=divs, materials=[mat]))
    dm = {d.division_id: d for d in r.division_margins}
    assert set(dm) == {"d1", "d2"}

    # d1 = A + B: выручка 2000 + 500 = 2500; маржа = сумма маржи продуктов
    pm = {p.product_id: p for p in r.product_margins.products}
    assert q(dm["d1"].revenue) == q(pm["a"].revenue + pm["b"].revenue)
    assert q(dm["d1"].margin) == q(pm["a"].margin + pm["b"].margin)
    assert dm["d1"].product_count == 2
    assert q(dm["d2"].revenue) == q(pm["c"].revenue)
    assert dm["d2"].product_count == 1
    # margin_share = margin / revenue
    assert dm["d1"].margin_share is not None
    assert q(dm["d1"].margin_share * 100) == q(dm["d1"].margin / dm["d1"].revenue * 100)


def test_division_absent_without_divisions():
    """Нет подразделений → отчёт пуст (и не попадает в снимок)."""
    n = 2
    a = Product(id="a", name="A", division_id="d1",
                piece_wage_per_unit=D(3))
    sales = [SalesLine(product_id="a", volume=[D(10)] * n, price=[D(100)] * n)]
    r = run(_model(n, [a], sales))            # divisions пуст
    assert r.division_margins == []


def test_product_without_recipe_or_division_excluded():
    """Продукт без рецептуры и продукт без division_id не входят в свёртку (без аллокации)."""
    n = 2
    a = Product(id="a", name="A", division_id="d1", piece_wage_per_unit=D(3))   # в свёртке
    b = Product(id="b", name="B", division_id="d1")                             # без рецептуры
    c = Product(id="c", name="C", piece_wage_per_unit=D(3))                     # без подразделения
    sales = [
        SalesLine(product_id="a", volume=[D(10)] * n, price=[D(100)] * n),
        SalesLine(product_id="b", volume=[D(5)] * n, price=[D(50)] * n),
        SalesLine(product_id="c", volume=[D(5)] * n, price=[D(50)] * n),
    ]
    divs = [Division(id="d1", name="Производство")]
    r = run(_model(n, [a, b, c], sales, divisions=divs))
    assert len(r.division_margins) == 1
    d1 = r.division_margins[0]
    # только A (с рецептурой, в d1); B без рецептуры и C без подразделения не входят
    assert d1.product_count == 1
    pm = {p.product_id: p for p in r.product_margins.products}
    assert q(d1.margin) == q(pm["a"].margin)


def test_dangling_division_id_ignored():
    """division_id, которого нет в справочнике → продукт не сворачивается (нет мусорной группы)."""
    n = 2
    a = Product(id="a", name="A", division_id="ghost", piece_wage_per_unit=D(3))
    sales = [SalesLine(product_id="a", volume=[D(10)] * n, price=[D(100)] * n)]
    divs = [Division(id="d1", name="Производство")]
    r = run(_model(n, [a], sales, divisions=divs))
    assert r.division_margins == []
