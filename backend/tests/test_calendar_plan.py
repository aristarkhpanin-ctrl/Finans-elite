"""Календарный план K0: этапы подготовительной фазы (SPEC §9).

Обычный этап → издержки подготовительного периода (C15) с признанием сразу (I21) или через
расходы будущих периодов (B15); этап-актив → ОС (C14/B14/I17). Числа выверены вручную;
балансовый инвариант B20=B34 обязан сходиться.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    CalendarPlan,
    Company,
    InvestmentPlan,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    Stage,
    StartingBalance,
)
from calc_core.money import quantize as q

D = Decimal


def _balanced(r) -> bool:
    return [q(v) for v in r.balance["B20"]] == [q(v) for v in r.balance["B34"]]


def _model(n, stages):
    return ProjectModel(
        header=ProjectHeader(name="cp", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(),
        investment_plan=InvestmentPlan(calendar=CalendarPlan(stages=stages)),
    )


def test_expense_stage_immediate():
    """Этап-издержка 600 за 3 мес (amortize=0): отток C15 и издержка I21 по 200/мес; B15=0."""
    n = 4
    st = Stage(id="s1", name="Лицензия", kind="expense", start_month=0, duration_months=3, cost=D(600))
    r = run(_model(n, [st]))
    assert [q(v) for v in r.cashflow["C15"]] == [D("200.00"), D("200.00"), D("200.00"), D("0.00")]
    assert [q(v) for v in r.income["I21"]] == [D("200.00"), D("200.00"), D("200.00"), D("0.00")]
    assert all(v == 0 for v in r.balance["B15"])
    assert _balanced(r)


def test_expense_stage_deferred_amortizes():
    """Этап 600 за 2 мес с капитализацией в РБП и списанием за 3 мес от финиша (мес. 2)."""
    n = 6
    st = Stage(id="s1", name="Пуск-наладка", kind="expense", start_month=0, duration_months=2,
               cost=D(600), amortize_months=3)
    r = run(_model(n, [st]))
    # деньги уходят по стройке (мес. 0,1 = 300); издержка признаётся при списании (мес. 2–4 = 200)
    assert [q(v) for v in r.cashflow["C15"]] == [D("300.00"), D("300.00"), D("0.00"),
                                                 D("0.00"), D("0.00"), D("0.00")]
    assert [q(v) for v in r.income["I21"]] == [D("0.00"), D("0.00"), D("200.00"),
                                               D("200.00"), D("200.00"), D("0.00")]
    # РБП (B15): растёт при стройке (300, 600), затем списывается (400, 200, 0)
    assert [q(v) for v in r.balance["B15"]] == [D("300.00"), D("600.00"), D("400.00"),
                                                D("200.00"), D("0.00"), D("0.00")]
    assert _balanced(r)


def test_asset_stage_capitalizes_and_depreciates():
    """Этап-актив 900 за 3 мес: ОС встаёт в месяц завершения (3), амортизируется за срок службы."""
    n = 6
    st = Stage(id="s1", name="Монтаж линии", kind="asset", start_month=0, duration_months=3,
               cost=D(900), asset_life_months=3)
    r = run(_model(n, [st]))
    # приобретение (C14) в месяц завершения (3); амортизация 300/мес (мес. 3–5)
    assert [q(v) for v in r.cashflow["C14"]] == [D("0.00"), D("0.00"), D("0.00"),
                                                 D("900.00"), D("0.00"), D("0.00")]
    assert [q(v) for v in r.balance["B14"]] == [D("0.00"), D("0.00"), D("0.00"),
                                                D("600.00"), D("300.00"), D("0.00")]
    assert [q(v) for v in r.income["I17"]] == [D("0.00"), D("0.00"), D("0.00"),
                                               D("300.00"), D("300.00"), D("300.00")]
    assert _balanced(r)


def test_empty_calendar_is_inert():
    """Пустой календарный план (по умолчанию) — нулевое воздействие на отчёты."""
    r = run(_model(3, []))
    assert all(v == 0 for v in r.cashflow["C15"])
    assert all(v == 0 for v in r.balance["B15"])
    assert _balanced(r)


# --- K1: связи-предшественники + иерархия ---

def test_predecessor_shifts_start():
    """Этап B начинается по завершении этапа A (финиш→старт, лаг 0)."""
    n = 5
    a = Stage(id="a", name="A", kind="expense", start_month=0, duration_months=2, cost=D(200))
    b = Stage(id="b", name="B", kind="expense", predecessor_id="a", start_month=0,
              duration_months=2, cost=D(400))
    r = run(_model(n, [a, b]))
    # A: 100/мес (мес. 0,1); B стартует в мес. 2 (финиш A): 200/мес (мес. 2,3)
    assert [q(v) for v in r.income["I21"]] == [D("100.00"), D("100.00"), D("200.00"),
                                               D("200.00"), D("0.00")]
    assert _balanced(r)


def test_predecessor_with_lag():
    """start_month у этапа со связью — это лаг после завершения предшественника."""
    n = 6
    a = Stage(id="a", name="A", kind="expense", start_month=0, duration_months=2, cost=D(200))
    b = Stage(id="b", name="B", kind="expense", predecessor_id="a", start_month=1,
              duration_months=1, cost=D(300))
    r = run(_model(n, [a, b]))
    # B стартует в мес. 3 (финиш A = 2, лаг 1): 300 в мес. 3
    assert [q(v) for v in r.income["I21"]] == [D("100.00"), D("100.00"), D("0.00"),
                                               D("300.00"), D("0.00"), D("0.00")]
    assert _balanced(r)


def test_group_stage_bears_no_cost():
    """Этап-группа (на который ссылаются как на parent) стоимости не несёт — только листья."""
    n = 3
    grp = Stage(id="g", name="Стройка", kind="expense", start_month=0, duration_months=3, cost=D(999))
    child = Stage(id="c", name="Фундамент", kind="expense", parent_id="g", start_month=0,
                  duration_months=1, cost=D(300))
    r = run(_model(n, [grp, child]))
    assert [q(v) for v in r.income["I21"]] == [D("300.00"), D("0.00"), D("0.00")]  # только ребёнок
    assert _balanced(r)


def test_dependency_cycle_does_not_hang():
    """Цикл связей (A→B→A) не зацикливает расчёт; баланс сходится."""
    n = 3
    a = Stage(id="a", name="A", kind="expense", predecessor_id="b", start_month=0,
              duration_months=1, cost=D(100))
    b = Stage(id="b", name="B", kind="expense", predecessor_id="a", start_month=1,
              duration_months=1, cost=D(100))
    r = run(_model(n, [a, b]))
    assert q(sum(r.income["I21"])) == D("200.00")  # обе издержки признаны
    assert _balanced(r)
