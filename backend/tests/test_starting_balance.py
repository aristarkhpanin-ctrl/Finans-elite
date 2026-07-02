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
from calc_core.money import quantize as q
from calc_core.models import (
    Company,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    StartingBalance,
)

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
