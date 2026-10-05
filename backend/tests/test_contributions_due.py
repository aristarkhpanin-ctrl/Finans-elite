"""Срок уплаты страховых взносов (0.9.54, пакет K, K1).

Взносы исчисляются с **начисленной** оплаты труда (ст. 424 НК РФ: дата выплаты для
взносов — день начисления) и уплачиваются до 28-го числа **следующего** месяца (п. 3
ст. 431) — когда бы ни выплачивалась сама зарплата. До 0.9.54 они уходили вместе с
зарплатой: на месяц раньше закона, а при задержке выплаты — позже.

Начисление не меняется (I6, I13–I15, маржа продуктов): загрузка ФОТ одна —
``pipeline.payroll_load``. Меняется только касса (C3, C6) и задолженность (B21).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    CostFunction,
    DirectCostKind,
    DirectCostLine,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StaffPosition,
)
from calc_core.money import quantize

d = Decimal


def _model(n: int, *, rate: str = "0.30", staff_delay: int = 0,
           piece_delay: int | None = None) -> ProjectModel:
    direct = []
    if piece_delay is not None:
        direct = [DirectCostLine(name="Сдельная оплата", kind=DirectCostKind.PIECE_WAGES,
                                 amount=[d(1000)] * n, payment_delay_months=piece_delay)]
    return ProjectModel(
        header=ProjectHeader(name="Взносы", duration_months=n),
        settings=ProjectSettings(payroll_contribution_rate=d(rate), profit_tax_rate=d(0),
                                 property_tax_rate=d(0), vat_rate=d(0)),
        operating_plan=OperatingPlan(
            products=[Product(id="p", name="Изделие")],
            sales=[SalesLine(product_id="p", volume=[d(10)] * n, price=[d(500)] * n)],
            direct_costs=direct,
            staff=[] if piece_delay is not None else [
                StaffPosition(name="Мастер", monthly_salary=d(1000),
                              function=CostFunction.STAFF_ADMIN,
                              payment_delay_months=staff_delay)],
        ),
    )


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def test_contributions_are_paid_the_month_after_accrual():
    r = run(_model(4))
    assert r.income["I13"] == [d(1300)] * 4                  # начисление — со взносами
    assert r.cashflow["C6"] == [d(1000), d(1300), d(1300), d(1300)]
    assert r.balance["B21"] == [d(300)] * 4                  # взносы месяца — до уплаты
    # Всё начисленное либо уплачено, либо стоит в задолженности: ничего не потеряно.
    assert sum(r.cashflow["C6"], d(0)) + r.balance["B21"][-1] == sum(r.income["I13"], d(0))
    assert _balanced(r)


def test_contributions_do_not_wait_for_a_delayed_wage():
    """Зарплата с задержкой на два месяца, взносы — всё равно в следующем: срок взносов
    привязан к начислению, а не к выплате."""
    r = run(_model(5, staff_delay=2))
    wages = [d(0), d(0), d(1000), d(1000), d(1000)]
    contributions = [d(0), d(300), d(300), d(300), d(300)]
    assert r.cashflow["C6"] == [w + c for w, c in zip(wages, contributions, strict=True)]
    assert r.balance["B23"] == [d(1000), d(2000), d(2000), d(2000), d(2000)]  # зарплата
    assert r.balance["B21"] == [d(300)] * 5                                   # взносы
    assert _balanced(r)


def test_piece_wage_contributions_follow_their_own_due_date():
    """Сдельная оплата с задержкой на два месяца: взносы с неё — в следующем месяце, а не
    вместе с выплатой; в детализации C3 они стоят своим слагаемым."""
    r = run(_model(4, piece_delay=2))
    assert r.cashflow["C3"] == [d(0), d(300), d(1300), d(1300)]
    assert r.balance["B23"][-1] == d(2000)
    assert r.balance["B21"][-1] == d(300)
    detail = next(x for x in r.details if x.code == "C3")
    items = {item.name: item.values for item in detail.items}
    assert items["Страховые взносы"] == [d(0), d(300), d(300), d(300)]
    assert [sum(col, d(0)) for col in zip(*items.values(), strict=True)] == r.cashflow["C3"]
    assert _balanced(r)


def test_december_contributions_are_due_in_january():
    """Месячный срок не знает «годовых» исключений: взносы за декабрь — в январе, а не в
    марте, как налог на прибыль за год."""
    m = _model(3)
    m.header.start_date = date(2026, 12, 1)
    r = run(m)
    assert r.cashflow["C6"] == [d(1000), d(1300), d(1300)]


def test_without_a_contribution_rate_there_is_nothing_to_defer():
    r = run(_model(3, rate="0"))
    assert r.cashflow["C6"] == [d(1000)] * 3
    assert r.balance["B21"] == [d(0)] * 3
    assert not any(x.code == "C3" for x in r.details)
