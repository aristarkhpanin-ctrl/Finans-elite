"""Рецептура продукта (BOM, SPEC §6/§8): нормы расхода материалов и сдельная ЗП на единицу.

BOM разворачивается в синтетические прямые издержки (тот же путь, что суммовые статьи):
потребление = производство × норма × цена; отсрочка/запас/импорт — свойствами материала.
Числа выверены вручную; инвариант B20=B34 обязан сходиться.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    BomLine,
    Company,
    Environment,
    Material,
    OperatingPlan,
    Product,
    ProductionLine,
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


def _model(n, products, sales, materials=None, production=None, fx_open=None):
    return ProjectModel(
        header=ProjectHeader(name="bom", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        company=Company(starting_balance=StartingBalance()),
        environment=Environment(fx_open=fx_open) if fx_open else Environment(),
        operating_plan=OperatingPlan(products=products, sales=sales,
                                     production=production or [], materials=materials or []),
    )


def test_bom_material_consumption():
    """Продукт: 10 шт/мес × 2 мес; норма 3 ед. материала по 5 ₽ → материалы 150 ₽/мес."""
    n = 2
    mat = Material(id="m1", name="Сталь", unit_price=D(5))
    prod = Product(id="p1", name="Изделие", bom=[BomLine(material_id="m1", qty_per_unit=D(3))])
    sales = SalesLine(product_id="p1", volume=[D(10)] * n, price=[D(100)] * n)
    r = run(_model(n, [prod], [sales], materials=[mat]))
    assert [q(v) for v in r.income["I5"]] == [D("150.00"), D("150.00")]   # материалы в с/с проданного
    assert [q(v) for v in r.cashflow["C2"]] == [D("150.00"), D("150.00")]  # оплата закупок
    assert [q(v) for v in r.income["I8"]] == [D("850.00"), D("850.00")]    # валовая прибыль
    assert _balanced(r)


def test_bom_piece_wage_per_unit():
    """Сдельная ЗП 7 ₽/ед. × 10 шт → I6 = 70/мес, деньги в C3."""
    n = 2
    prod = Product(id="p1", name="Изделие", piece_wage_per_unit=D(7))
    sales = SalesLine(product_id="p1", volume=[D(10)] * n, price=[D(100)] * n)
    r = run(_model(n, [prod], [sales]))
    assert [q(v) for v in r.income["I6"]] == [D("70.00"), D("70.00")]
    assert [q(v) for v in r.cashflow["C3"]] == [D("70.00"), D("70.00")]
    assert _balanced(r)


def test_bom_material_terms_flow_through():
    """Свойства материала работают: отсрочка оплаты создаёт кредиторку B23."""
    n = 3
    mat = Material(id="m1", name="Сырьё", unit_price=D(10), payment_delay_months=1)
    prod = Product(id="p1", name="Изделие", bom=[BomLine(material_id="m1", qty_per_unit=D(2))])
    sales = SalesLine(product_id="p1", volume=[D(5), D(5), D(0)], price=[D(100)] * 3)
    r = run(_model(n, [prod], [sales], materials=[mat]))
    # потребление 100/мес (мес. 0,1); оплата сдвинута на 1 мес → C2 в мес. 1,2; B23 = 100 в мес. 0,1
    assert [q(v) for v in r.cashflow["C2"]] == [D("0.00"), D("100.00"), D("100.00")]
    assert [q(v) for v in r.balance["B23"]] == [D("100.00"), D("100.00"), D("0.00")]
    assert _balanced(r)


def test_bom_follows_production_plan():
    """Расход материала привязан к производству (план производства), а не к продажам."""
    n = 2
    mat = Material(id="m1", unit_price=D(1))
    prod = Product(id="p1", name="Изделие", bom=[BomLine(material_id="m1", qty_per_unit=D(1))])
    sales = SalesLine(product_id="p1", volume=[D(10), D(10)], price=[D(50)] * 2)
    production = ProductionLine(product_id="p1", volume=[D(20), D(0)])  # всё производим в мес. 0
    r = run(_model(n, [prod], [sales], materials=[mat], production=[production]))
    assert [q(v) for v in r.cashflow["C2"]] == [D("20.00"), D("0.00")]   # закупка при производстве
    assert [q(v) for v in r.income["I5"]] == [D("10.00"), D("10.00")]    # с/с признаётся при продаже
    assert q(r.balance["B5"][0]) == D("10.00")                            # остаток ГП на конец мес. 0
    assert _balanced(r)


def test_foreign_material_in_bom():
    """Импортный материал в рецептуре: потребление по курсу закупки (fx_open=50)."""
    n = 1
    mat = Material(id="m1", unit_price=D(2), foreign=True)   # 2 ед. валюты за единицу
    prod = Product(id="p1", name="Экспортный", bom=[BomLine(material_id="m1", qty_per_unit=D(1))])
    sales = SalesLine(product_id="p1", volume=[D(10)], price=[D(500)])
    r = run(_model(n, [prod], [sales], materials=[mat], fx_open=D(50)))
    assert q(r.income["I5"][0]) == D("1000.00")   # 10 × 1 × 2 × 50
    assert _balanced(r)


def test_products_without_bom_are_inert():
    """Модель без рецептур (как все существующие) — прямых издержек из BOM нет."""
    n = 2
    prod = Product(id="p1", name="Изделие")
    sales = SalesLine(product_id="p1", volume=[D(10)] * n, price=[D(100)] * n)
    mat = Material(id="m1", unit_price=D(5))   # справочник есть, рецептур нет
    r = run(_model(n, [prod], [sales], materials=[mat]))
    assert all(v == 0 for v in r.income["I5"])
    assert all(v == 0 for v in r.income["I6"])
    assert _balanced(r)


# --- M1: маржа по продуктам ---

def test_product_margins_report():
    """Маржа по продуктам: A с рецептурой (в отчёте), B без (не в отчёте);
    суммовые прямые издержки — отдельной строкой «нераспределённые»."""
    from calc_core.models import DirectCostLine

    n = 2
    mat = Material(id="m1", name="Сталь", unit_price=D(5))
    a = Product(id="a", name="A", bom=[BomLine(material_id="m1", qty_per_unit=D(3))],
                piece_wage_per_unit=D(7))
    b = Product(id="b", name="B")                      # без рецептуры — маржа не определена
    sales = [
        SalesLine(product_id="a", volume=[D(10)] * n, price=[D(100)] * n),
        SalesLine(product_id="b", volume=[D(4)] * n, price=[D(50)] * n),
    ]
    model = _model(n, [a, b], sales, materials=[mat])
    model.operating_plan.direct_costs = [DirectCostLine(name="прочее", amount=[D(30)] * n)]
    pm = run(model).product_margins
    assert [p.product_id for p in pm.products] == ["a"]     # только продукт со спецификацией
    p = pm.products[0]
    assert q(p.revenue) == D("2000.00")                     # 10×100×2 мес
    assert q(p.bom_cost) == D("300.00")                     # 10×3×5×2
    assert q(p.piece_wages) == D("140.00")                  # 10×7×2
    assert q(p.margin) == D("1560.00")
    assert p.margin_share is not None and q(p.margin_share * 100) == D("78.00")
    assert q(pm.unallocated_direct) == D("60.00")           # суммовая статья 30×2


def test_product_margins_absent_without_bom():
    """Без рецептур отчёт пуст (и не попадает в снимок результата)."""
    n = 2
    prod = Product(id="p1", name="Изделие")
    sales = SalesLine(product_id="p1", volume=[D(10)] * n, price=[D(100)] * n)
    pm = run(_model(n, [prod], [sales])).product_margins
    assert pm.products == [] and pm.unallocated_direct == 0


# --- Целостность рецептуры: висячая ссылка на удалённый материал ---

def test_dangling_material_is_reported_not_silent():
    """Ссылка на несуществующий материал пропускается, но об этом сообщается.

    Иначе удаление материала молча занизило бы себестоимость и завысило прибыль —
    пользователь увидел бы более выгодный проект и не узнал, почему.
    """
    mat = Material(id="m1", name="Сталь", unit_price=D(5))
    prod = Product(id="p1", name="Изделие", bom=[
        BomLine(material_id="m1", qty_per_unit=D(3)),
        BomLine(material_id="m_removed", qty_per_unit=D(7)),   # материала больше нет
    ])
    sales = SalesLine(product_id="p1", volume=[D(10)] * 2, price=[D(100)] * 2)
    r = run(_model(2, [prod], [sales], materials=[mat]))

    # учтён только существующий материал: 10 × 3 × 5 = 150
    assert [q(v) for v in r.income["I5"]] == [D("150.00"), D("150.00")]
    assert any("m_removed" in w and "Изделие" in w for w in r.warnings)
    assert _balanced(r)


def test_intact_recipe_is_quiet():
    """Модель без висячих ссылок предупреждений о рецептуре не даёт — правило инертно."""
    mat = Material(id="m1", name="Сталь", unit_price=D(5))
    prod = Product(id="p1", name="Изделие", bom=[BomLine(material_id="m1", qty_per_unit=D(3))])
    sales = SalesLine(product_id="p1", volume=[D(10)] * 2, price=[D(100)] * 2)
    r = run(_model(2, [prod], [sales], materials=[mat]))
    assert not any("рецептура" in w.lower() for w in r.warnings)


def test_dangling_material_named_once_per_product():
    """Повторные ссылки на один и тот же материал не размножают предупреждение."""
    prod = Product(id="p1", name="Изделие", bom=[
        BomLine(material_id="нет", qty_per_unit=D(1)),
        BomLine(material_id="нет", qty_per_unit=D(2)),
    ])
    sales = SalesLine(product_id="p1", volume=[D(10)], price=[D(100)])
    r = run(_model(1, [prod], [sales], materials=[]))
    assert sum("нет" in w for w in r.warnings) == 1


def test_dangling_material_hits_margins_too():
    """Маржа продукта считается по тем же учтённым материалам — отчёт и аналитика согласны."""
    mat = Material(id="m1", name="Сталь", unit_price=D(5))
    prod = Product(id="p1", name="Изделие", bom=[
        BomLine(material_id="m1", qty_per_unit=D(3)),
        BomLine(material_id="призрак", qty_per_unit=D(7)),
    ])
    sales = SalesLine(product_id="p1", volume=[D(10)], price=[D(100)])
    r = run(_model(1, [prod], [sales], materials=[mat]))
    pm = r.product_margins.products[0]
    assert q(pm.bom_cost) == D("150.00")          # без «призрака», как и в I5
    assert any("призрак" in w for w in r.warnings)
