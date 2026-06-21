"""Тесты запасов (5.1b): сырьё (B3) и готовая продукция (B5)."""
from decimal import Decimal

from calc_core import run
from calc_core.engine.inventory import finished_goods, purchase_schedule
from calc_core.samples import build_sample_project
from calc_core.series import cumulative, sub


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
