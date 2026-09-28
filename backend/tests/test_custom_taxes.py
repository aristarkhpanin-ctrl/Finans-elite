"""Тесты настраиваемых налогов (SPEC §22.9, gap 2.1, фаза T0).

Базы — по предварительному прогону (Q2); уплата по периодичности (Q5, хвост в B21);
отнесение expense → I21 / profit → I24 (Q4); ошибка формулы — ModelError (Q6);
пустой список инертен; балансовый инвариант держится (движок проверяет сам).
"""
from decimal import Decimal

import pytest

from calc_core import run
from calc_core.engine import ModelError
from calc_core.models import ProjectModel
from calc_core.models.environment import Tax
from calc_core.models.operating import OperatingPlan, Product, SalesLine
from calc_core.samples import build_sample_project


def _model(n=12, volume=10, price=1000) -> ProjectModel:
    model = ProjectModel()
    model.header.duration_months = n
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[SalesLine(product_id="p1", volume=[Decimal(volume)] * n,
                         price=[Decimal(price)] * n)],
    )
    return model


def test_revenue_tax_expense_allocation():
    """База «выручка»: начисление = I1 × ставка → I21, уплата — в следующем месяце → C12."""
    model = _model()
    model.environment.taxes = [Tax(name="Сбор 1%", rate=Decimal("0.01"), base="revenue")]
    base = run(_model())                      # без налога
    result = run(model)
    expected = [v * Decimal("0.01") for v in base.income["I1"]]
    assert result.income["I21"] == expected
    # вычитаемый налог даёт налоговый щит: I27 падает на ставку налога на прибыль от
    # начисления (ставка — из модели: прежние «20%» здесь стояли числом и пережили закон)
    rate = model.settings.profit_tax_rate
    shield = [base.income["I27"][t] - result.income["I27"][t] for t in range(12)]
    assert shield == [v * rate for v in expected]
    # Сбор и налог на прибыль платятся в следующем месяце (декабрьский налог на прибыль —
    # в марте, за горизонтом): разница кассы — начисление прошлого месяца за вычетом щита.
    assert result.cashflow["C12"][0] == base.cashflow["C12"][0]
    assert result.cashflow["C12"][1:] == [base.cashflow["C12"][t] + expected[t - 1]
                                          - shield[t - 1] for t in range(1, 12)]
    # Задолженность — ровно начисленное в текущем месяце (уплата — в следующем).
    assert [result.balance["B21"][t] - base.balance["B21"][t] for t in range(12)] \
        == [expected[t] - shield[t] for t in range(12)]
    assert result.income["I28"][0] < base.income["I28"][0]


def test_profit_allocation_does_not_reduce_tax_base():
    """Отнесение «за счёт прибыли»: начисление в I24, налоговая база (I26) не меняется."""
    model = _model()
    model.environment.taxes = [Tax(name="Из прибыли", rate=Decimal("0.01"),
                                   base="revenue", allocation="profit")]
    base = run(_model())
    result = run(model)
    assert result.income["I26"] == base.income["I26"]        # база налога на прибыль та же
    expected = [v * Decimal("0.01") for v in base.income["I1"]]
    assert result.income["I24"] == expected
    assert [base.income["I28"][t] - result.income["I28"][t] for t in range(12)] == expected


def test_quarterly_payment_and_b21():
    """Квартальная уплата: в месяце после квартала (апрель, июль, октябрь), между — долг
    в B21; IV квартал платится в январе — за горизонтом."""
    model = _model()
    # allocation='profit' → налогового щита нет, дельты C12/B21 — чистый настраиваемый налог
    model.environment.taxes = [Tax(name="Квартальный", rate=Decimal("0.10"),
                                   base="revenue", periodicity="quarter",
                                   allocation="profit")]
    base = run(_model())
    result = run(model)
    monthly = [v * Decimal("0.10") for v in base.income["I1"]]
    extra_cash = [result.cashflow["C12"][t] - base.cashflow["C12"][t] for t in range(12)]
    for t in range(12):
        if t in (3, 6, 9):
            assert extra_cash[t] == sum(monthly[t - 3:t], Decimal(0))
        else:
            assert extra_cash[t] == 0
    # B21 (сверх задолженности базы — налог на прибыль тоже платится через месяц):
    # копится весь квартал и до уплаты; в месяце уплаты — только новое
    debt = [result.balance["B21"][t] - base.balance["B21"][t] for t in range(12)]
    assert debt[0] == monthly[0]
    assert debt[2] == monthly[0] + monthly[1] + monthly[2]
    assert debt[3] == monthly[3]
    assert debt[11] == sum(monthly[9:12], Decimal(0))


def test_yearly_tail_stays_in_b21():
    """Годовая уплата на горизонте 14 мес.: год — в январе (мес. 12), хвост висит в B21."""
    model = _model(n=14)
    model.environment.taxes = [Tax(name="Годовой", rate=Decimal("0.10"),
                                   base="revenue", periodicity="year",
                                   allocation="profit")]
    base = run(_model(n=14))
    result = run(model)
    monthly = [v * Decimal("0.10") for v in base.income["I1"]]
    extra_cash = [result.cashflow["C12"][t] - base.cashflow["C12"][t] for t in range(14)]
    assert extra_cash[12] == sum(monthly[:12], Decimal(0))
    assert sum(extra_cash[:12], Decimal(0)) == 0 and extra_cash[13] == 0
    assert result.balance["B21"][13] - base.balance["B21"][13] \
        == monthly[12] + monthly[13]                                 # честная задолженность


def test_payroll_property_profit_bases():
    """Пресеты баз: ФОТ (I6+I13+I14+I15), имущество (B13+B14), прибыль (МАКС(I26,0))."""
    model = build_sample_project()
    base = run(model)
    for base_kind, expected_series in [
        ("payroll", [base.income["I6"][t] + base.income["I13"][t] + base.income["I14"][t]
                     + base.income["I15"][t] for t in range(base.n)]),
        ("property", [base.balance["B13"][t] + base.balance["B14"][t]
                      for t in range(base.n)]),
        ("profit", [max(base.income["I26"][t], Decimal(0)) for t in range(base.n)]),
    ]:
        taxed = build_sample_project()
        taxed.environment.taxes = [Tax(name="Т", rate=Decimal("0.02"), base=base_kind,
                                       allocation="profit")]   # profit-отнесение: I26 не дрейфует
        result = run(taxed)
        got = [result.income["I24"][t] - base.income["I24"][t] for t in range(base.n)]
        assert got == [v * Decimal("0.02") for v in expected_series], base_kind


def test_formula_base():
    """База-формула над строками предварительного прогона (положительный кэш-фло)."""
    model = _model()
    model.environment.taxes = [Tax(name="Форм", rate=Decimal("0.05"), base="formula",
                                   formula="МАКС(C13, 0)")]
    base = run(_model())
    result = run(model)
    expected = [max(base.cashflow["C13"][t], Decimal(0)) * Decimal("0.05") for t in range(12)]
    assert [result.income["I21"][t] - base.income["I21"][t] for t in range(12)] == expected


def test_formula_error_rejects_model():
    model = _model()
    model.environment.taxes = [Tax(name="Битый", rate=Decimal("0.05"), base="formula",
                                   formula="I1 +")]
    with pytest.raises(ModelError, match="Битый"):
        run(model)


def test_empty_taxes_inert():
    """Пустой список налогов → числа в точности как раньше (golden-инертность)."""
    plain = run(_model())
    with_empty = _model()
    with_empty.environment.taxes = []
    again = run(with_empty)
    assert plain.income["I28"] == again.income["I28"]
    assert plain.cashflow["C29"] == again.cashflow["C29"]
    assert plain.balance["B21"] == again.balance["B21"]


def test_c12_detail_includes_custom_tax():
    """Детализация C12 (Q7): профильные + настраиваемый; Σ слагаемых = C12."""
    model = _model()
    model.settings.vat_rate = Decimal("0.20")
    model.environment.taxes = [Tax(name="Экосбор", rate=Decimal("0.01"), base="revenue")]
    result = run(model)
    d = next(d for d in result.details if d.code == "C12")
    names = {i.name for i in d.items}
    assert "Экосбор" in names and "Налог на прибыль" in names
    total = [sum((i.values[t] for i in d.items), Decimal(0)) for t in range(12)]
    assert total == result.cashflow["C12"]


def test_taxes_with_auto_financing_invariant():
    """Налоги учитываются в потребности автоподбора; инварианты движок проверяет сам."""
    model = _model(price=100)
    model.financing.auto_financing.enabled = True
    model.financing.auto_financing.annual_rate = Decimal("0.20")
    model.environment.taxes = [Tax(name="Сбор", rate=Decimal("0.10"), base="revenue",
                                   periodicity="quarter")]
    result = run(model)                        # InvariantError не поднялся → баланс сошёлся
    assert result.balance["B20"] == result.balance["B34"]
