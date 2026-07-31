"""Аналитика Финанс-Аудит: аналитическая форма, тренды, коэффициенты (фаза C).

Числа выведены вручную — проверяется методика, а не совпадение со снимком.
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze
from audit_core.analysis import (
    CURRENT_ASSETS,
    GROSS_PROFIT,
    NET_PROFIT,
    OPERATING_PROFIT,
    PROFIT_BEFORE_TAX,
    TOTAL_ASSETS,
    TOTAL_EQLIAB,
)
from audit_core.models import AuditPeriod, AuditSubjectModel

D = Decimal


def _model(kind: str = "year", n: int = 2) -> AuditSubjectModel:
    """Простой субъект: актив 200/250 = пассив; выручка 500/600."""
    return AuditSubjectModel(
        periods=[AuditPeriod(label=f"P{i + 1}", kind=kind) for i in range(n)],
        balance={
            "A_FIXED": [D(100), D(120)],
            "A_INVENTORY": [D(30), D(35)],
            "A_RECEIVABLE": [D(40), D(45)],
            "A_CASH": [D(30), D(50)],
            "P_EQUITY": [D(120), D(150)],
            "P_LONG": [D(30), D(30)],
            "P_SHORT": [D(50), D(70)],
        },
        income={
            "I_REVENUE": [D(500), D(600)],
            "I_COGS": [D(300), D(360)],
            "I_OPEX": [D(80), D(90)],
            "I_INTEREST": [D(10), D(12)],
            "I_OTHER": [D(0), D(0)],
            "I_TAX": [D(22), D(28)],
        },
    )


def _line(lines, code):
    return next(ln for ln in lines if ln.code == code)


def _ratio(r, group, name):
    return r.ratios[group][name]


def test_analytical_form_subtotals():
    """Подытоги — арифметика над введённым: оборотные, итоги, прибыли по цепочке."""
    r = analyze(_model())
    assert _line(r.balance, CURRENT_ASSETS).values == [D(100), D(130)]   # 30+40+30, 35+45+50
    assert _line(r.balance, TOTAL_ASSETS).values == [D(200), D(250)]
    assert _line(r.balance, TOTAL_EQLIAB).values == [D(200), D(250)]
    assert _line(r.income, GROSS_PROFIT).values == [D(200), D(240)]      # 500−300
    assert _line(r.income, OPERATING_PROFIT).values == [D(120), D(150)]  # 200−80
    assert _line(r.income, PROFIT_BEFORE_TAX).values == [D(110), D(138)]  # 120−10+0
    assert _line(r.income, NET_PROFIT).values == [D(88), D(110)]         # 110−22
    assert r.balanced is True and r.balance_gap == [D(0), D(0)]


def test_horizontal_analysis():
    """Первый период — база (None); далее Δ и темп к предыдущему."""
    r = analyze(_model())
    rev = next(t for t in r.horizontal if t.code == "I_REVENUE")
    assert rev.delta == [None, D(100)]
    assert rev.rate == [None, D(100) / D(500)]          # +20%
    assets = next(t for t in r.horizontal if t.code == TOTAL_ASSETS)
    assert assets.delta == [None, D(50)]


def test_vertical_analysis_bases():
    """Доли: баланс — от суммарного актива, ОПУ — от выручки."""
    r = analyze(_model())
    cash = next(s for s in r.vertical if s.code == "A_CASH")
    assert cash.share == [D(30) / D(200), D(50) / D(250)]
    cogs = next(s for s in r.vertical if s.code == "I_COGS")
    assert cogs.share == [D(300) / D(500), D(360) / D(600)]


def test_ratios_year():
    """Годовые периоды: коэффициенты по прямым формулам, без приведения."""
    r = analyze(_model())
    assert _ratio(r, "liquidity", "Коэффициент текущей ликвидности") == [D(100) / D(50), D(130) / D(70)]
    assert _ratio(r, "liquidity", "Коэффициент срочной ликвидности") == [D(70) / D(50), D(95) / D(70)]
    assert _ratio(r, "liquidity", "Чистый оборотный капитал") == [D(50), D(60)]
    assert _ratio(r, "gearing", "Коэффициент автономии") == [D(120) / D(200), D(150) / D(250)]
    assert _ratio(r, "gearing", "Суммарные обязательства к активам") == [D(80) / D(200), D(100) / D(250)]
    assert _ratio(r, "gearing", "Коэффициент покрытия процентов") == [D(120) / D(10), D(150) / D(12)]
    assert _ratio(r, "profitability", "Рентабельность чистой прибыли") == [D(88) / D(500), D(110) / D(600)]
    assert _ratio(r, "profitability", "Рентабельность активов (ROA)") == [D(88) / D(200), D(110) / D(250)]
    # оборачиваемость активов за год = выручка / активы
    assert _ratio(r, "activity", "Оборачиваемость активов") == [D(500) / D(200), D(600) / D(250)]
    # период оборота запасов = запасы / себестоимость × 365
    assert _ratio(r, "activity", "Период оборачиваемости запасов, дн.")[0] == D(30) * D(365) / D(300)


def test_quarterly_annualisation():
    """Квартал: потоковые показатели приводятся к году (×4), «в днях» — по длине периода."""
    y = analyze(_model("year"))
    q = analyze(_model("quarter"))
    # ROA квартала = годовой ROA × (365/91.25) = ×4 относительно того же баланса
    roa_y = _ratio(y, "profitability", "Рентабельность активов (ROA)")[0]
    roa_q = _ratio(q, "profitability", "Рентабельность активов (ROA)")[0]
    assert roa_q == roa_y * (D(365) / D("91.25"))
    # маржа (доля в выручке) от периодичности не зависит
    assert (_ratio(q, "profitability", "Рентабельность чистой прибыли")
            == _ratio(y, "profitability", "Рентабельность чистой прибыли"))
    # период оборота в днях считается по длине периода
    assert _ratio(q, "activity", "Период оборачиваемости запасов, дн.")[0] == D(30) * D("91.25") / D(300)


def test_undefined_instead_of_zero():
    """Нулевая база → None («не определён»), а не 0."""
    m = _model()
    m.balance["P_SHORT"] = [D(0), D(0)]
    m.income["I_REVENUE"] = [D(0), D(0)]
    r = analyze(m)
    assert _ratio(r, "liquidity", "Коэффициент текущей ликвидности") == [None, None]
    assert _ratio(r, "profitability", "Рентабельность чистой прибыли") == [None, None]
    assert next(s for s in r.vertical if s.code == "I_COGS").share == [None, None]


def test_unbalanced_input_warns():
    """Несходящийся баланс: разрыв и предупреждение, расчёт по введённому как есть."""
    m = _model()
    m.balance["P_EQUITY"] = [D(120), D(999)]
    r = analyze(m)
    assert r.balanced is False
    assert r.balance_gap[1] == D(250) - D(1099)
    assert r.warnings and "не сходится" in r.warnings[0]


def test_empty_model_is_inert():
    """Без периодов анализ пуст (не падает)."""
    r = analyze(AuditSubjectModel())
    assert r.n == 0 and r.balance == [] and r.ratios == {}
