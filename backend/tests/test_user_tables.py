"""Таблицы пользователя F1: строки-формулы над результатом расчёта.

Ошибки формул не роняют расчёт; пустые таблицы инертны (не попадают в снимок).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Company,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
    UserRow,
    UserTable,
)
from calc_core.money import quantize as q
from calc_core.serialize import result_to_dict

D = Decimal


def _model(tables):
    sales = SalesLine(product_id="p1", volume=[D(10), D(20)], price=[D(100)] * 2)
    return ProjectModel(
        header=ProjectHeader(name="ut", start_date=date(2026, 1, 1), duration_months=2),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(products=[Product(id="p1", name="P")], sales=[sales]),
        user_tables=tables,
    )


def test_user_table_rows_computed():
    """Формулы над строками отчётов: ряд, свёртка-скаляр (broadcast) и функция."""
    table = UserTable(id="t1", name="Аналитика", rows=[
        UserRow(name="Выручка ×2", formula="I1 * 2"),
        UserRow(name="Итого продаж", formula="СУММ(I1)"),
        UserRow(name="Накопленная касса", formula="АККУМ(C13)"),
    ])
    r = run(_model([table]))
    t = r.user_tables[0]
    assert t.name == "Аналитика" and len(t.rows) == 3
    assert [q(v) for v in t.rows[0].values] == [D("2000.00"), D("4000.00")]
    assert [q(v) for v in t.rows[1].values] == [D("3000.00"), D("3000.00")]  # скаляр → константа
    assert [q(v) for v in t.rows[2].values] == [D("1000.00"), D("3000.00")]
    assert all(row.error is None for row in t.rows)


def test_formula_error_does_not_break_calc():
    """Ошибочная строка получает сообщение и нули; соседняя строка и расчёт — целы."""
    table = UserTable(id="t1", rows=[
        UserRow(name="Битая", formula="Z99 +"),
        UserRow(name="Живая", formula="I1"),
    ])
    r = run(_model([table]))
    bad, good = r.user_tables[0].rows
    assert bad.error is not None and all(v == 0 for v in bad.values)
    assert good.error is None and q(good.values[0]) == D("1000.00")
    assert q(r.income["I1"][0]) == D("1000.00")   # отчёты не пострадали


def test_empty_tables_are_inert():
    r = run(_model([]))
    assert r.user_tables == []
    assert "user_tables" not in result_to_dict(r)


def test_tables_in_snapshot_when_present():
    table = UserTable(id="t1", name="Т", rows=[UserRow(name="х", formula="N")])
    snap = result_to_dict(run(_model([table])))
    assert "user_tables" in snap
    rows = snap["user_tables"][0]["rows"]
    assert rows[0]["values"] == ["2.00", "2.00"]   # N = 2 (горизонт), broadcast
