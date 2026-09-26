"""Финансовый разрез сметы (бюджетный Гантт): освоение ≠ оплата, трактовка, S-кривые.

Смета — аналитический выход: она **читает** те же величины, что уходят в отчёты, и не имеет
права с ними разойтись. Поэтому оплата в смете проверяется против оттока C15, а разрыв
«начислено − оплачено» — против кредиторки B23.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.engine.calendar import compute_budget
from calc_core.models import (
    CalendarPlan,
    Company,
    InvestmentPlan,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    Resource,
    Stage,
    StageResource,
    StartingBalance,
)
from calc_core.money import quantize as q

D = Decimal


def _model(n, stages, resources=None):
    return ProjectModel(
        header=ProjectHeader(name="bf", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(),
        investment_plan=InvestmentPlan(
            calendar=CalendarPlan(stages=stages, resources=resources or [])),
    )


def _row(budget, sid):
    return next(r for r in budget.stages if r.id == sid)


def test_empty_calendar_stays_inert():
    """Без этапов смета пуста — бюджетный разрез ничего не выдумывает."""
    b = compute_budget(_model(6, []), 6)
    assert b.stages == [] and b.total == 0
    assert b.monthly_cash == [] and b.payables == []


def test_accrual_and_cash_differ_by_payment_delay():
    """Освоение идёт по графику работ, оплата — со сдвигом на отсрочку ресурса."""
    stages = [Stage(id="s", name="Стройка", kind="expense", start_month=0, duration_months=2,
                    resources=[StageResource(resource_id="r", quantity=D(2))])]
    resources = [Resource(id="r", name="Подрядчик", unit_price=D(300),
                          payment_delay_months=2)]
    model = _model(6, stages, resources)
    b = compute_budget(model, 6)

    assert b.monthly == [D(300), D(300), D(0), D(0), D(0), D(0)]        # 600 за 2 мес
    assert b.monthly_cash == [D(0), D(0), D(300), D(300), D(0), D(0)]   # сдвиг на 2 мес
    assert b.total == D(600)


def test_payables_equal_accrued_minus_paid():
    """Разрыв накопленных рядов — обязательства перед подрядчиком (та же величина, что B23)."""
    stages = [Stage(id="s", kind="expense", start_month=0, duration_months=2,
                    resources=[StageResource(resource_id="r", quantity=D(2))])]
    resources = [Resource(id="r", unit_price=D(300), payment_delay_months=2)]
    model = _model(6, stages, resources)
    b = compute_budget(model, 6)
    r = run(model)

    assert b.payables == [D(300), D(600), D(300), D(0), D(0), D(0)]
    # смета не расходится с отчётами: кредиторка и отток совпадают с движком
    assert [q(v) for v in r.balance["B23"]] == [q(v) for v in b.payables]
    assert [q(v) for v in r.cashflow["C15"]] == [q(v) for v in b.monthly_cash]


def test_direct_cost_paid_without_delay():
    """Прямая стоимость (без ресурсов) платится в момент освоения."""
    b = compute_budget(_model(4, [Stage(id="s", kind="expense", start_month=1,
                                        duration_months=2, cost=D(400))]), 4)
    assert b.monthly == [D(0), D(200), D(200), D(0)]
    assert b.monthly_cash == b.monthly
    assert b.payables == [D(0)] * 4


def test_asset_stage_cash_equals_accrual():
    """Этап-актив ставится разово в месяц финиша; отсрочки машинерия активов не применяет."""
    stages = [Stage(id="a", kind="asset", start_month=0, duration_months=3, cost=D(900),
                    asset_life_months=12,
                    resources=[StageResource(resource_id="r", quantity=D(1))])]
    resources = [Resource(id="r", unit_price=D(900), payment_delay_months=2)]
    b = compute_budget(_model(6, stages, resources), 6)
    assert b.monthly == [D(0), D(0), D(0), D(900), D(0), D(0)]
    assert b.monthly_cash == b.monthly      # оплата совпадает с постановкой на баланс


def test_cumulative_curves():
    """S-кривые: накопленное освоение и накопленная оплата."""
    b = compute_budget(_model(4, [Stage(id="s", kind="expense", start_month=0,
                                        duration_months=2, cost=D(200))]), 4)
    assert b.cumulative == [D(100), D(200), D(200), D(200)]
    assert b.cumulative_cash == b.cumulative


def test_treatment_split_sums_to_total():
    """Разбивка по трактовке: издержки периода / РБП / капвложения; Σ = смета."""
    stages = [
        Stage(id="e", kind="expense", start_month=0, duration_months=1, cost=D(100)),
        Stage(id="d", kind="expense", start_month=0, duration_months=1, cost=D(200),
              amortize_months=6),
        Stage(id="a", kind="asset", start_month=0, duration_months=1, cost=D(300),
              asset_life_months=12),
        Stage(id="p", kind="production", start_month=0, duration_months=1),
    ]
    b = compute_budget(_model(12, stages), 12)
    assert b.expense_total == D(100)      # признаётся сразу (I21)
    assert b.deferred_total == D(200)     # расходы будущих периодов (B15)
    assert b.asset_total == D(300)        # капвложение (C14 → B14)
    assert b.expense_total + b.deferred_total + b.asset_total == b.total == D(600)
    assert _row(b, "p").treatment == "none"        # производство стоимости не несёт


def test_stage_rows_carry_monthly_series():
    """У строки этапа свои помесячные ряды — из них Гантт рисует деньги под полосой."""
    stages = [Stage(id="s", kind="expense", start_month=1, duration_months=2, cost=D(400))]
    b = compute_budget(_model(4, stages), 4)
    row = _row(b, "s")
    assert row.monthly == [D(0), D(200), D(200), D(0)]
    assert row.monthly_cash == row.monthly
    assert row.treatment == "expense"


def test_group_rolls_up_series_and_treatment():
    """Группа сворачивает ряды потомков; трактовка общая — если она у потомков одна."""
    stages = [
        Stage(id="g", name="Подготовка"),
        Stage(id="c1", parent_id="g", kind="expense", start_month=0, duration_months=1,
              cost=D(100)),
        Stage(id="c2", parent_id="g", kind="expense", start_month=1, duration_months=1,
              cost=D(50)),
    ]
    b = compute_budget(_model(4, stages), 4)
    g = _row(b, "g")
    assert g.monthly == [D(100), D(50), D(0), D(0)]
    assert g.cost == D(150)
    assert g.treatment == "expense"


def test_mixed_group_treatment_is_not_guessed():
    """Смешанной группе трактовка одного из потомков не приписывается."""
    stages = [
        Stage(id="g", name="Смешанная"),
        Stage(id="c1", parent_id="g", kind="expense", start_month=0, duration_months=1,
              cost=D(100)),
        Stage(id="c2", parent_id="g", kind="asset", start_month=0, duration_months=1,
              cost=D(300), asset_life_months=12),
    ]
    b = compute_budget(_model(4, stages), 4)
    assert _row(b, "g").treatment == "mixed"


def test_budget_totals_match_monthly_sums():
    """Смета сходится сама с собой: Σ помесячного освоения = итог (в пределах горизонта)."""
    stages = [
        Stage(id="s1", kind="expense", start_month=0, duration_months=3, cost=D(600)),
        Stage(id="s2", kind="asset", start_month=1, duration_months=2, cost=D(900),
              asset_life_months=24),
    ]
    b = compute_budget(_model(12, stages), 12)
    assert sum(b.monthly) == b.total == D(1500)
    assert sum(b.monthly_cash) == b.total
