"""Тесты доходов участников (SPEC §17, пакет №7, U0).

Акционеры: −C21 + C26 (+ терминальная стоимость B33); кредиторы: по займам из графика
движка (валютные — в рублях по FX). Пустое финансирование инертно.
"""
from decimal import Decimal

from calc_core import run
from calc_core.models import ProjectModel
from calc_core.models.financing import EquityInjection, Loan
from calc_core.models.operating import OperatingPlan, Product, SalesLine
from calc_core.samples import build_sample_project
from calc_core.serialize import result_to_dict


def _model(n=24) -> ProjectModel:
    model = ProjectModel()
    model.header.duration_months = n
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[SalesLine(product_id="p1", volume=[Decimal(10)] * n,
                         price=[Decimal(1000)] * n)],
    )
    return model


def _by_id(result, pid):
    return next((p for p in result.participants if p.id == pid), None)


def test_lender_irr_equals_loan_rate():
    """Кредитор bullet-займа получает ровно ставку займа (рублёвый заём)."""
    model = _model()
    model.financing.loans = [Loan(name="Банк", amount=Decimal(1_000_000), start_month=0,
                                  term_months=12, annual_rate=Decimal("0.20"),
                                  repayment="bullet")]
    result = run(model)
    lender = _by_id(result, "loan:0")
    assert lender is not None and lender.kind == "lender"
    assert lender.invested == Decimal(1_000_000)
    assert lender.irr_annual is not None
    assert abs(lender.irr_annual - Decimal("0.20")) < Decimal("0.0001")
    assert lender.withdrawn > lender.invested          # тело + проценты


def test_lender_flow_matches_statement_lines():
    """Σ потоков кредиторов = C23 + C24 − C22 (займы — единственный кредитный контур)."""
    model = _model()
    model.financing.loans = [
        Loan(name="А", amount=Decimal(500_000), start_month=0, term_months=10),
        Loan(name="Б", amount=Decimal(300_000), start_month=3, term_months=12),
    ]
    result = run(model)
    lenders = [p for p in result.participants if p.kind == "lender"]
    assert len(lenders) == 2
    total = [sum(p.flow[t] for p in lenders) for t in range(result.n)]
    cf = result.cashflow
    expected = [cf["C23"][t] + cf["C24"][t] - cf["C22"][t] for t in range(result.n)]
    assert total == expected


def test_equity_flow_and_terminal_value():
    """Акционеры: поток = C26 − C21; вариант с TV добавляет B33 в последний месяц."""
    model = _model()
    model.financing.equity = [EquityInjection(amount=Decimal(2_000_000), month=0)]
    model.financing.dividends = [Decimal(0)] * 12 + [Decimal(50_000)] * 12
    result = run(model)
    eq = _by_id(result, "equity")
    assert eq is not None and eq.kind == "equity"
    cf = result.cashflow
    assert eq.flow == [cf["C26"][t] - cf["C21"][t] for t in range(result.n)]
    assert eq.invested == Decimal(2_000_000)
    assert eq.withdrawn == sum(cf["C26"], Decimal(0))
    assert eq.terminal_value == result.balance["B33"][result.n - 1]
    # с терминальной стоимостью метрики строго лучше (изъятие добавилось)
    assert eq.npv_with_terminal is not None and eq.npv_with_terminal > eq.npv
    assert eq.irr_with_terminal_annual is not None


def test_foreign_loan_fx_gain_for_lender():
    """Валютный заём при росте курса: рублёвая доходность кредитора выше валютной ставки."""
    n = 13
    model = _model(n=n)
    model.environment.fx_open = Decimal("100")
    model.environment.fx_rate = [Decimal(100) + Decimal(2) * Decimal(t) for t in range(n)]
    model.financing.loans = [Loan(name="Вал", amount=Decimal(10_000), start_month=0,
                                  term_months=12, annual_rate=Decimal("0.05"),
                                  repayment="bullet", foreign=True)]
    result = run(model)
    lender = _by_id(result, "loan:0")
    assert lender.irr_annual is not None
    assert lender.irr_annual > Decimal("0.05")         # курсовой доход поверх ставки


def test_lender_terminal_value_for_truncated_loan():
    """Заём с графиком за горизонтом: без TV IRR занижена, с TV — равна ставке.

    Равное погашение тела с term=12 при n=12: последний платёж тела в месяце 12 —
    за горизонтом; остаток требования уходит в терминальную стоимость кредитора.
    """
    model = _model(n=12)
    model.financing.loans = [Loan(name="Обрезанный", amount=Decimal(120_000),
                                  start_month=0, term_months=12,
                                  annual_rate=Decimal("0.18"))]
    result = run(model)
    lender = _by_id(result, "loan:0")
    assert lender.terminal_value == Decimal(10_000)     # 1/12 тела не успела вернуться
    assert lender.irr_with_terminal_annual is not None
    assert abs(lender.irr_with_terminal_annual - Decimal("0.18")) < Decimal("0.0001")
    assert lender.irr_annual is None or lender.irr_annual < lender.irr_with_terminal_annual


def test_no_financing_inert():
    result = run(_model())
    assert result.participants == []
    assert "participants" not in result_to_dict(result)


def test_snapshot_contains_participants():
    """Golden-снимок включает участников при непустом финансировании."""
    result = run(build_sample_project())
    snapshot = result_to_dict(result)
    if result.participants:                            # демо содержит заём/капитал
        names = {p["name"] for p in snapshot["participants"]}
        assert len(names) == len(result.participants)


def test_loan_outside_horizon_skipped():
    model = _model(n=6)
    model.financing.loans = [Loan(name="Поздний", amount=Decimal(100), start_month=24)]
    result = run(model)
    assert all(p.kind != "lender" for p in result.participants)


def test_participants_in_calc_response(client):
    """/calculate отдаёт participants для демо (акционеры + займы)."""
    sample = client.get("/api/v1/sample").json()
    body = client.post("/api/v1/calculate", json=sample).json()
    kinds = {p["kind"] for p in body["participants"]}
    assert kinds == {"equity", "lender"}
    eq = next(p for p in body["participants"] if p["kind"] == "equity")
    assert eq["name"] == "Акционеры" and len(eq["flow"]) == body["n"]
