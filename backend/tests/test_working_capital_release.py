"""Закрытие расчётов на конец горизонта (0.9.57, пакет K, K4).

Поток проекта видит деньги только внутри горизонта, а расчёты на его конец открыты:
дебиторка за последние месяцы, налог за последний год, долг поставщикам. До 0.9.57 они в
показатели не попадали — и ошибка шла в обе стороны: неуплаченный налог завышал NPV,
неинкассированная дебиторка занижала. Теперь в последнем месяце поток показателей
получает высвобождение оборотного капитала — отдельным, названным объектом.
"""
from __future__ import annotations

from decimal import Decimal

from calc_core import run
from calc_core.integrator import consolidate
from calc_core.metrics import annual_to_monthly
from calc_core.models import (
    DirectCostKind,
    DirectCostLine,
    OperatingPlan,
    PaymentTerms,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)
from calc_core.reports.horizon import RELEASED

d = Decimal
N = 12
EPS = d("0.00001")


def _model(*, release: bool = True, name: str = "Торговля") -> ProjectModel:
    """Покупатели платят через месяц, поставщикам — через месяц, налог за год — в марте:
    на конец горизонта открыты дебиторка, кредиторка и налоги."""
    return ProjectModel(
        header=ProjectHeader(name=name, duration_months=N),
        settings=ProjectSettings(profit_tax_rate=d("0.25"), discount_rate_annual=d("0.20"),
                                 profit_tax_periodicity="quarter",
                                 release_working_capital=release),
        operating_plan=OperatingPlan(
            products=[Product(id="p", name="Товар")],
            sales=[SalesLine(product_id="p", volume=[d(100)] * N, price=[d(1000)] * N,
                             payment=PaymentTerms(payment_delay_months=1))],
            direct_costs=[DirectCostLine(name="Закупка", kind=DirectCostKind.MATERIALS,
                                         amount=[d(60_000)] * N, payment_delay_months=1)],
        ),
    )


def _pre_release(r) -> list[Decimal]:
    cf = r.cashflow
    return [cf["C13"][t] + cf["C8"][t] - cf["C9"][t] + cf["C20"][t] for t in range(r.n)]


def test_open_positions_are_closed_in_the_last_month():
    r = run(_model())
    rel = r.working_capital_release
    assert rel.enabled and rel.month == N - 1
    items = {i.code: i.amount for i in rel.items}
    assert items["B2"] == r.balance["B2"][-1] > 0          # дебиторка приходит
    assert items["B23"] == -r.balance["B23"][-1] < 0       # кредиторка уходит
    assert items["B21"] == -r.balance["B21"][-1] < 0       # налог за IV квартал уходит
    assert abs(rel.total - sum(items.values(), d(0))) < EPS
    flow, pre = r.project_flow, _pre_release(r)
    assert all(abs(flow[t] - pre[t]) < EPS for t in range(N - 1))
    assert abs(flow[-1] - pre[-1] - rel.total) < EPS


def test_the_release_lists_every_open_working_capital_line_and_nothing_else():
    """Перечень закрыт: строки баланса вне него (деньги, основные средства, долг) в
    закрытие не входят — их стоимость не вопрос расчётов."""
    assert [code for code, _ in RELEASED] == ["B2", "B3", "B4", "B5", "B7", "B21", "B23",
                                              "B24"]
    r = run(_model())
    assert {i.code for i in r.working_capital_release.items} <= {c for c, _ in RELEASED}


def test_npv_moves_by_exactly_the_discounted_release():
    on, off = run(_model()), run(_model(release=False))
    rate = annual_to_monthly(d("0.20"))
    expected = on.working_capital_release.total / (1 + rate) ** (N - 1)
    assert abs((on.metrics.npv - off.metrics.npv) - expected) < EPS


def test_switched_off_it_is_still_named_but_not_counted():
    r = run(_model(release=False))
    rel = r.working_capital_release
    assert rel.enabled is False and rel.total > 0
    assert "выключено" in rel.note and "не видят" in rel.note
    pre = _pre_release(r)
    assert all(abs(r.project_flow[t] - pre[t]) < EPS for t in range(N))


def test_the_statements_and_gordon_do_not_move():
    """Закрытие — только в потоке показателей: касса, баланс и модель Гордона (у неё
    бизнес продолжается, капитал не высвобождается) от него не зависят."""
    on, off = run(_model()), run(_model(release=False))
    assert on.cashflow["C29"] == off.cashflow["C29"]
    assert on.balance["B20"] == off.balance["B20"]
    assert on.valuation.gordon_value == off.valuation.gordon_value


def test_the_note_names_the_sum_and_what_is_left_out():
    rel = run(_model()).working_capital_release
    assert "последнем месяце" in rel.note and "₽" in rel.note
    assert "Основные средства в закрытие не входят" in rel.note


def test_nothing_open_means_nothing_to_close():
    m = ProjectModel(header=ProjectHeader(name="Пусто", duration_months=3))
    rel = run(m).working_capital_release
    assert rel.items == [] and rel.total == 0 and "закрывать нечего" in rel.note


def test_the_group_sums_the_projects_and_names_those_left_out():
    """Поток холдинга — сумма потоков проектов, поэтому в закрытие группы входят только
    проекты с включённым закрытием; остальные названы, а не растворены в сумме."""
    a, b = _model(name="Первый"), _model(release=False, name="Второй")
    group = consolidate([a, b], d("0.20"))
    ra = run(a).working_capital_release
    rel = group.working_capital_release
    assert rel.enabled and abs(rel.total - ra.total) < EPS
    assert "«Второй»" in rel.note and "в свод не входят" in rel.note
    assert abs(group.project_flow[-1]
               - (run(a).project_flow[-1] + run(b).project_flow[-1])) < EPS


def test_the_api_returns_the_release_with_its_note(client, register):
    headers = register()
    pid = client.post("/api/v1/projects", json={"name": "П", "model": _model().model_dump(
        mode="json")}, headers=headers).json()["id"]
    body = client.post(f"/api/v1/projects/{pid}/calculate", headers=headers).json()
    rel = body["working_capital_release"]
    assert rel["enabled"] is True and rel["month"] == N - 1
    assert {i["code"] for i in rel["items"]} == {"B2", "B21", "B23"}
    assert rel["note"].startswith("Показатели эффективности считаются с закрытием")
