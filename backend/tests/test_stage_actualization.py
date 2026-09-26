"""Тесты актуализации этапов календарного плана (план-факт сметы, gap 4.6, SA0).

Факт-даты/стоимость этапа + отклонения в смете; свёртка факта групп. План не меняется;
пустой факт инертен. Расчёт отчётов идёт на плане (контроль реализации — не пересчёт).
"""
from decimal import Decimal

from calc_core import run
from calc_core.engine.calendar import compute_budget
from calc_core.models import (
    CalendarPlan,
    InvestmentPlan,
    OperatingPlan,
    ProjectModel,
    Stage,
)

D = Decimal


def _model(stages, n=12) -> ProjectModel:
    model = ProjectModel()
    model.header.duration_months = n
    model.operating_plan = OperatingPlan()
    model.investment_plan = InvestmentPlan(calendar=CalendarPlan(stages=stages))
    return model


def _row(budget, sid):
    return next(s for s in budget.stages if s.id == sid)


def test_leaf_actual_and_variance():
    """Факт стоимости/финиша листа → cost_variance и schedule_variance."""
    st = Stage(id="s1", name="Стройка", kind="expense", start_month=0, duration_months=3,
               cost=D(1000), actual_cost=D(1250), actual_start_month=0, actual_finish_month=5)
    b = compute_budget(_model([st]), 12)
    row = _row(b, "s1")
    assert row.cost == D(1000) and row.finish_month == 3
    assert row.actual_cost == D(1250)
    assert row.cost_variance == D(250)               # перерасход 250
    assert row.actual_finish_month == 5
    assert row.schedule_variance_months == 2         # опоздание на 2 мес.
    assert b.actual_total == D(1250)


def test_no_actual_is_inert():
    """Без факта — факт-поля None, отклонений нет, план как прежде."""
    st = Stage(id="s1", name="Э", kind="expense", start_month=0, duration_months=2, cost=D(500))
    b = compute_budget(_model([st]), 12)
    row = _row(b, "s1")
    assert row.cost == D(500)
    assert row.actual_cost is None and row.cost_variance is None
    assert row.schedule_variance_months is None
    assert b.actual_total is None


def test_group_rolls_up_fact():
    """Группа сворачивает факт потомков: Σ стоимостей, min старт, max финиш."""
    grp = Stage(id="g", name="Стройка", kind="expense", start_month=0, duration_months=6)
    c1 = Stage(id="c1", name="Фундамент", kind="expense", parent_id="g", start_month=0,
               duration_months=2, cost=D(400), actual_cost=D(500),
               actual_start_month=0, actual_finish_month=3)
    c2 = Stage(id="c2", name="Стены", kind="expense", parent_id="g", start_month=2,
               duration_months=2, cost=D(600), actual_cost=D(600),
               actual_start_month=3, actual_finish_month=5)
    b = compute_budget(_model([grp, c1, c2]), 12)
    g = _row(b, "g")
    assert g.cost == D(1000)                          # план: сумма листьев
    assert g.actual_cost == D(1100)                   # факт: 500 + 600
    assert g.actual_start_month == 0 and g.actual_finish_month == 5
    assert g.cost_variance == D(100)
    assert b.actual_total == D(1100)


def test_partial_fact_group():
    """Факт только у части потомков: группа сворачивает имеющееся."""
    grp = Stage(id="g", name="Гр", kind="expense", start_month=0, duration_months=4)
    c1 = Stage(id="c1", name="A", kind="expense", parent_id="g", start_month=0,
               duration_months=2, cost=D(300), actual_cost=D(350))
    c2 = Stage(id="c2", name="B", kind="expense", parent_id="g", start_month=2,
               duration_months=2, cost=D(200))                # без факта
    b = compute_budget(_model([grp, c1, c2]), 12)
    g = _row(b, "g")
    assert g.actual_cost == D(350)                    # только c1
    assert b.actual_total == D(350)


def test_plan_reports_unchanged_by_fact():
    """Факт не влияет на расчёт отчётов: план-числа те же с фактом и без."""
    base = Stage(id="s1", name="Актив", kind="asset", start_month=0, duration_months=2,
                 cost=D(10000), asset_life_months=12)
    withfact = Stage(id="s1", name="Актив", kind="asset", start_month=0, duration_months=2,
                     cost=D(10000), asset_life_months=12,
                     actual_cost=D(12000), actual_finish_month=4)
    r0 = run(_model([base]))
    r1 = run(_model([withfact]))
    assert r0.cashflow["C14"] == r1.cashflow["C14"]   # capex на плане
    assert r0.balance["B14"] == r1.balance["B14"]     # ОС на плане
    assert r0.income["I17"] == r1.income["I17"]        # амортизация на плане


def test_empty_calendar_budget_empty():
    b = compute_budget(_model([]), 12)
    assert b.stages == [] and b.actual_total is None
