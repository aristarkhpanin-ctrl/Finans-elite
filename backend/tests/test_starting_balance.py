"""Детальный стартовый баланс (SPEC §14): стартовая дебиторка/кредиторка действующего
предприятия. Дебиторка инкассируется (C1), кредиторка оплачивается (C2) в первом месяце;
они участвуют в проверке сходимости стартового баланса. Числа выверены вручную.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from calc_core import run
from calc_core.engine.errors import ModelError
from calc_core.models import (
    Company,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    StartingBalance,
)
from calc_core.money import quantize as q

D = Decimal


def _balanced(r) -> bool:
    return [q(v) for v in r.balance["B20"]] == [q(v) for v in r.balance["B34"]]


def _model(sb: StartingBalance, n=2) -> ProjectModel:
    return ProjectModel(
        header=ProjectHeader(name="sb", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        company=Company(starting_balance=sb),
        operating_plan=OperatingPlan(),
    )


def test_opening_receivables_and_payables_unwind_to_cash():
    """Старт: касса 1000, дебиторка 500, кредиторка 300 (уравновешены капиталом 1200).

    В мес. 0: инкассация 500 (C1), оплата 300 (C2) → касса 1200; дебиторка/кредиторка → 0.
    """
    sb = StartingBalance(cash=D(1000), receivables=D(500), payables=D(300),
                         paid_in_capital=D(1200))
    r = run(_model(sb))
    assert [q(v) for v in r.cashflow["C1"]] == [D("500.00"), D("0.00")]
    assert [q(v) for v in r.cashflow["C2"]] == [D("300.00"), D("0.00")]
    assert [q(v) for v in r.balance["B1"]] == [D("1200.00"), D("1200.00")]
    assert all(v == 0 for v in r.balance["B2"])    # стартовая дебиторка инкассирована
    assert all(v == 0 for v in r.balance["B23"])   # стартовая кредиторка оплачена
    assert _balanced(r)


def test_opening_inventory_is_static_standing_level():
    """Стартовые запасы (сырьё 4000 + ГП 6000, уравновешены капиталом 10000) — поддерживаемый
    уровень: остаются в B3/B5 постоянно, денежного потока не создают."""
    sb = StartingBalance(raw_materials=D(4000), finished_goods=D(6000), paid_in_capital=D(10000))
    r = run(_model(sb))
    assert [q(v) for v in r.balance["B3"]] == [D("4000.00"), D("4000.00")]
    assert [q(v) for v in r.balance["B5"]] == [D("6000.00"), D("6000.00")]
    assert all(v == 0 for v in r.balance["B1"])   # запасы статичны — кассу не трогают
    assert _balanced(r)


def test_opening_working_capital_participates_in_convergence():
    """Старт, сходившийся без оборотного капитала, становится несходящимся с дебиторкой."""
    # касса 1000 = капитал 1000 — сходится; дебиторка 500 без покрытия — разрыв.
    bad = StartingBalance(cash=D(1000), receivables=D(500), paid_in_capital=D(1000))
    with pytest.raises(ModelError):
        run(_model(bad))
    # та же дебиторка, уравновешенная капиталом, — сходится.
    good = StartingBalance(cash=D(1000), receivables=D(500), paid_in_capital=D(1500))
    assert _balanced(run(_model(good)))


def test_opening_short_term_debt_is_carried_in_b22():
    """Стартовый краткосрочный долг (400, уравновешен кассой 1000 и капиталом 600) несётся
    в B22 постоянно (как долгосрочный долг в B26): авто-погашения нет, кассу не трогает."""
    sb = StartingBalance(cash=D(1000), short_term_debt=D(400), paid_in_capital=D(600))
    r = run(_model(sb))
    assert [q(v) for v in r.balance["B22"]] == [D("400.00"), D("400.00")]   # несётся, не гасится
    assert [q(v) for v in r.balance["B1"]] == [D("1000.00"), D("1000.00")]  # долг статичен — касса неизменна
    assert [q(v) for v in r.balance["B25"]] == [D("400.00"), D("400.00")]   # входит в краткосрочные обязательства
    assert _balanced(r)


def test_opening_short_term_debt_participates_in_convergence():
    """Краткосрочный долг участвует в проверке сходимости стартового баланса."""
    # долг 400 без покрытия в активах (касса лишь 600) — разрыв.
    bad = StartingBalance(cash=D(600), short_term_debt=D(400), paid_in_capital=D(600))
    with pytest.raises(ModelError):
        run(_model(bad))
    # тот же долг, покрытый кассой, — сходится.
    good = StartingBalance(cash=D(1000), short_term_debt=D(400), paid_in_capital=D(600))
    assert _balanced(run(_model(good)))


def test_opening_equity_structure_is_carried():
    """Полная стартовая структура капитала: привилегированные акции (B28), резервы (B30),
    добавочный капитал (B31) — несутся постоянно и входят в собственный капитал B33."""
    sb = StartingBalance(cash=D(1000), paid_in_capital=D(400), preferred_capital=D(200),
                         reserves=D(150), additional_capital=D(250))
    r = run(_model(sb))
    assert [q(v) for v in r.balance["B28"]] == [D("200.00"), D("200.00")]
    assert [q(v) for v in r.balance["B30"]] == [D("150.00"), D("150.00")]
    assert [q(v) for v in r.balance["B31"]] == [D("250.00"), D("250.00")]
    # собственный капитал = 400 + 200 + 150 + 250 = 1000
    assert [q(v) for v in r.balance["B33"]] == [D("1000.00"), D("1000.00")]
    assert _balanced(r)


def test_opening_equity_participates_in_convergence():
    """Стартовые резервы/капитал участвуют в проверке сходимости."""
    bad = StartingBalance(cash=D(500), reserves=D(200), paid_in_capital=D(500))
    with pytest.raises(ModelError):
        run(_model(bad))
    good = StartingBalance(cash=D(700), reserves=D(200), paid_in_capital=D(500))
    assert _balanced(run(_model(good)))
