"""Незавершённое производство (НЗП, B4): производственный цикл (SPEC §6).

Стоимость запуска (материалы+труд) и выпуск ГП сдвигаются на длину цикла; «в пути»
стоимость лежит в B4. Себестоимость (I5/I6) признаётся при продаже готовой продукции.
Числа выведены вручную; баланс B20=B34 сходится. При cycle=0 НЗП отсутствует (B4≡0).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Company,
    DirectCostLine,
    OperatingPlan,
    Product,
    ProductionLine,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.models.common import DirectCostKind

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def _model(n, cycle, tp, tq, price, materials, wages):
    """Один продукт: план производства tp, продажи tq по цене price; материалы/сдельный труд."""
    direct = [DirectCostLine(name="m", kind=DirectCostKind.MATERIALS, amount=materials)]
    if any(w != 0 for w in wages):
        direct.append(DirectCostLine(name="w", kind=DirectCostKind.PIECE_WAGES, amount=wages))
    return ProjectModel(
        header=ProjectHeader(name="wip", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0"),
                                 production_cycle_months=cycle),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p0", name="p0")],
            sales=[SalesLine(product_id="p0", volume=tq, price=price)],
            production=[ProductionLine(product_id="p0", volume=tp)],
            direct_costs=direct,
        ),
    )


def test_one_month_cycle_holds_cost_in_wip():
    """Цикл 1 мес.: запуск 10 ед. (1000 матер. + 500 труд) в t0 → выпуск в t1, продажа в t2.

    НЗП B4=1500 в t0; в t1 стоимость переходит в ГП (B5=1500); при продаже в t2 —
    себестоимость I5=1000, I6=500, B5→0.
    """
    n = 4
    r = run(_model(n, cycle=1,
                   tp=[D(10), D(0), D(0), D(0)],
                   tq=[D(0), D(0), D(10), D(0)],
                   price=[D(200)] * n,
                   materials=[D(1000), D(0), D(0), D(0)],
                   wages=[D(500), D(0), D(0), D(0)]))
    assert [quantize(v) for v in r.balance["B4"]] == [D("1500.00"), D("0.00"), D("0.00"), D("0.00")]
    assert [quantize(v) for v in r.balance["B5"]] == [D("0.00"), D("1500.00"), D("0.00"), D("0.00")]
    assert [quantize(v) for v in r.income["I5"]] == [D("0.00"), D("0.00"), D("1000.00"), D("0.00")]
    assert [quantize(v) for v in r.income["I6"]] == [D("0.00"), D("0.00"), D("500.00"), D("0.00")]
    assert _balanced(r)


def test_two_month_cycle_accumulates_wip():
    """Цикл 2 мес.: запуск в t0 → выпуск ГП в t2 → продажа в t3.

    НЗП держится 2 месяца (t0, t1); в t2 — готовая продукция (B5=1000); себестоимость
    I5=1000 признаётся при продаже в t3.
    """
    n = 5
    r = run(_model(n, cycle=2,
                   tp=[D(10), D(0), D(0), D(0), D(0)],
                   tq=[D(0), D(0), D(0), D(10), D(0)],
                   price=[D(200)] * n,
                   materials=[D(1000), D(0), D(0), D(0), D(0)],
                   wages=[D(0)] * n))
    assert [quantize(v) for v in r.balance["B4"]] == [
        D("1000.00"), D("1000.00"), D("0.00"), D("0.00"), D("0.00")]
    assert [quantize(v) for v in r.balance["B5"]] == [
        D("0.00"), D("0.00"), D("1000.00"), D("0.00"), D("0.00")]
    assert [quantize(v) for v in r.income["I5"]] == [
        D("0.00"), D("0.00"), D("0.00"), D("1000.00"), D("0.00")]
    assert _balanced(r)


def test_zero_cycle_has_no_wip():
    """Без цикла (cycle=0): НЗП отсутствует (B4≡0), выпуск = запуску."""
    n = 3
    r = run(_model(n, cycle=0,
                   tp=[D(10), D(0), D(0)],
                   tq=[D(10), D(0), D(0)],
                   price=[D(200)] * n,
                   materials=[D(1000), D(0), D(0)],
                   wages=[D(0)] * n))
    assert all(v == 0 for v in r.balance["B4"])
    assert _balanced(r)
