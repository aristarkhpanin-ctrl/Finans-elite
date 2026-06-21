"""Курсовая разница I25: переоценка валютной позиции (SPEC §3, §22.3).

Монетарный актив во второй валюте переоценивается по курсу FX[t]; изменение его
стоимости в основной валюте — курсовая разница I25 (доход при росте курса). Стоимость
позиции отражается в B6; баланс сходится. Числа выведены вручную.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Company,
    Environment,
    Financing,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    StartingBalance,
)

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def _fx_model(fx_open: str, fx_rate, profit_tax: str = "0") -> ProjectModel:
    """100 ед. валюты (опорный курс fx_open), оплачены капиталом; курс растёт по fx_rate."""
    n = len(fx_rate)
    fm = D(100)
    return ProjectModel(
        header=ProjectHeader(name="fx", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D(profit_tax),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        environment=Environment(fx_open=D(fx_open), fx_rate=[D(x) for x in fx_rate]),
        # стартовый баланс: валютный актив 100×fx_open уравновешен капиталом
        company=Company(starting_balance=StartingBalance(
            foreign_monetary=fm, paid_in_capital=fm * D(fx_open))),
        operating_plan=OperatingPlan(),
        financing=Financing(common_shares=D(100)),
    )


def test_fx_revaluation_gain_no_tax():
    """Курс 60 → 70 → 80: позиция 100 ед. даёт +1000 курсовой разницы каждый период."""
    r = run(_fx_model(fx_open="60", fx_rate=["70", "80"]))
    assert r.income["I25"] == [D(1000), D(1000)]      # 100×(70−60), 100×(80−70)
    assert r.income["I28"] == [D(1000), D(1000)]      # налога нет → чистая = курсовая
    assert r.balance["B6"] == [D(7000), D(8000)]      # 100×70, 100×80 в основной валюте
    assert r.balance["B32"] == [D(1000), D(2000)]     # накопленная прибыль
    assert _balanced(r)


def test_fx_revaluation_loss_when_rate_falls():
    """Курс падает 60 → 55: позиция обесценивается → курсовой убыток −500."""
    r = run(_fx_model(fx_open="60", fx_rate=["55"]))
    assert r.income["I25"] == [D(-500)]               # 100×(55−60)
    assert r.balance["B6"] == [D(5500)]
    assert _balanced(r)


def test_fx_gain_is_taxed_and_balance_holds():
    """Курсовая разница входит в налоговую базу: налог 20% от 1000 = 200, чистая 800."""
    r = run(_fx_model(fx_open="60", fx_rate=["70"], profit_tax="0.20"))
    assert r.income["I25"] == [D(1000)]
    assert r.income["I27"] == [D(200)]                # налог на курсовую разницу
    assert r.income["I28"] == [D(800)]
    assert _balanced(r)


def test_no_fx_rate_means_no_revaluation():
    """Без второй валюты (пустой fx_rate) курсовой разницы нет — поведение прежнее."""
    m = ProjectModel(
        header=ProjectHeader(duration_months=3),
        settings=ProjectSettings(profit_tax_rate=D("0"), vat_rate=D("0")),
    )
    r = run(m)
    assert all(v == 0 for v in r.income["I25"])
    assert all(v == 0 for v in r.balance["B6"])
    assert _balanced(r)
