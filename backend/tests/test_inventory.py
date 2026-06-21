"""Тесты запасов (5.1b): сырьё (B3) и готовая продукция (B5)."""
from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.engine.inventory import finished_goods, purchase_schedule
from calc_core.models import (
    DirectCostLine,
    InventoryMethod,
    OperatingPlan,
    ProductionLine,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)
from calc_core.models.common import DirectCostKind
from calc_core.samples import build_sample_project
from calc_core.series import cumulative, sub

D = Decimal


def test_purchase_schedule_lead():
    # потребление в t=1 и t=2, закупка за 1 мес → сырьё на складе в t=0 и t=1
    purch, raw = purchase_schedule([Decimal(0), Decimal(100), Decimal(100)], 1, 3)
    assert purch == [Decimal(100), Decimal(100), Decimal(0)]
    assert raw == [Decimal(100), Decimal(100), Decimal(0)]
    # тождество B3 = cum(закупки) − cum(потребление)
    assert raw == sub(cumulative(purch), cumulative([Decimal(0), Decimal(100), Decimal(100)]))


def test_purchase_schedule_no_lead_is_regression():
    consumption = [Decimal(50), Decimal(70)]
    purch, raw = purchase_schedule(consumption, 0, 2)
    assert purch == consumption
    assert raw == [Decimal(0), Decimal(0)]


def test_finished_goods_accumulates_and_draws_down():
    # производим 120/80, продаём 100/100; себестоимость 48000/32000 мат + 12000/8000 ЗП
    cogs_m, cogs_w, b5, warns = finished_goods(
        produced_units=[Decimal(120), Decimal(80)],
        sold_units=[Decimal(100), Decimal(100)],
        materials_value=[Decimal(48000), Decimal(32000)],
        wages_value=[Decimal(12000), Decimal(8000)],
        n=2,
    )
    assert cogs_m == [Decimal(40000), Decimal(40000)]
    assert cogs_w == [Decimal(10000), Decimal(10000)]
    assert b5 == [Decimal(10000), Decimal(0)]   # запас в t=0, распродан в t=1
    assert warns == []
    # тождество B5 = cum(производств. стоимость) − cum(COGS)
    prod_cost = [Decimal(60000), Decimal(40000)]
    cogs = [Decimal(50000), Decimal(50000)]
    assert b5 == sub(cumulative(prod_cost), cumulative(cogs))


def test_finished_goods_produce_to_sell_no_inventory():
    cogs_m, cogs_w, b5, warns = finished_goods(
        produced_units=[Decimal(100), Decimal(100)],
        sold_units=[Decimal(100), Decimal(100)],
        materials_value=[Decimal(40000), Decimal(40000)],
        wages_value=[Decimal(10000), Decimal(10000)],
        n=2,
    )
    assert b5 == [Decimal(0), Decimal(0)]
    assert cogs_m == [Decimal(40000), Decimal(40000)]  # вся стоимость в себестоимости


def test_oversell_warns_and_caps():
    cogs_m, cogs_w, b5, warns = finished_goods(
        produced_units=[Decimal(50)],
        sold_units=[Decimal(80)],
        materials_value=[Decimal(5000)],
        wages_value=[Decimal(0)],
        n=1,
    )
    assert warns  # продажи превысили запас — предупреждение
    assert b5 == [Decimal(0)]


def test_sample_has_inventory_and_sells_out():
    r = run(build_sample_project())
    assert any(v != 0 for v in r.balance["B3"])  # сырьё
    assert any(v != 0 for v in r.balance["B5"])  # готовая продукция
    # к концу горизонта всё произведённое продано (производство = сбыт суммарно)
    assert r.balance["B5"][r.n - 1] == Decimal(0)


def test_fifo_vs_average_with_changing_cost():
    """Партии с разной себестоимостью: ФИФО списывает раннюю, средняя — усредняет."""
    args = dict(produced_units=[D(10), D(10), D(0)], sold_units=[D(0), D(10), D(10)],
                materials_value=[D(100), D(200), D(0)], wages_value=[D(0), D(0), D(0)], n=3)
    cm_f, _, b5_f, _ = finished_goods(**args, method=InventoryMethod.FIFO)
    cm_a, _, b5_a, _ = finished_goods(**args, method=InventoryMethod.AVERAGE)
    assert cm_f == [D(0), D(100), D(200)]    # ФИФО: сначала ранняя (дешёвая) партия
    assert cm_a == [D(0), D(150), D(150)]    # средняя себестоимость
    assert b5_f == [D(100), D(200), D(0)]    # t0: партия 100 ещё на складе
    # тождество запаса B5 = cum(стоимость) − cum(COGS) сохраняется для ФИФО
    assert b5_f == sub(cumulative([D(100), D(200), D(0)]), cumulative(cm_f))


def _inv_method_project(method: InventoryMethod) -> ProjectModel:
    """Выпуск 10/10/0 при себестоимости 100/200/0; продажи 0/10/10 (запас между периодами)."""
    n = 3
    return ProjectModel(
        header=ProjectHeader(name="inv", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(profit_tax_rate=D("0"), vat_rate=D("0"),
                                 inventory_method=method),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Изделие")],
            sales=[SalesLine(product_id="p1", volume=[D(0), D(10), D(10)],
                             price=[D(100), D(100), D(100)])],
            production=[ProductionLine(product_id="p1", volume=[D(10), D(10), D(0)])],
            direct_costs=[DirectCostLine(name="мат", kind=DirectCostKind.MATERIALS,
                                         amount=[D(100), D(200), D(0)])],
        ),
    )


def test_engine_inventory_method_changes_cogs_keeps_balance():
    rf = run(_inv_method_project(InventoryMethod.FIFO))
    ra = run(_inv_method_project(InventoryMethod.AVERAGE))
    assert rf.income["I5"] == [D(0), D(100), D(200)]    # ФИФО
    assert ra.income["I5"] == [D(0), D(150), D(150)]    # средняя
    for r in (rf, ra):
        for t in range(r.n):
            assert abs(r.balance["B20"][t] - r.balance["B34"][t]) <= Decimal("0.01")
