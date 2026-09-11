"""Тесты периодичности уплаты профильных налогов (SPEC §11, gap 2.3, PP0).

Прибыль и НДС платятся в последнем месяце периода; начисление не меняется, отсрочка → B21.
Месяц (по умолчанию) = текущее поведение → golden без дрейфа.
"""
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Financing,
    OperatingPlan,
    Product,
    ProjectModel,
    SalesLine,
)
from calc_core.models.common import DirectCostKind
from calc_core.models.operating import DirectCostLine
from calc_core.money import almost_equal


def _model(n=12, vat="0", profit_period="month", vat_period="month") -> ProjectModel:
    model = ProjectModel()
    model.header.duration_months = n
    model.settings.vat_rate = Decimal(vat)
    model.settings.profit_tax_periodicity = profit_period
    model.settings.vat_periodicity = vat_period
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[SalesLine(product_id="p1", volume=[Decimal(20)] * n, price=[Decimal(1000)] * n)],
        direct_costs=[DirectCostLine(name="Мат", kind=DirectCostKind.MATERIALS,
                                     amount=[Decimal(3000)] * n)],
    )
    model.financing = Financing()
    return model


def test_month_periodicity_matches_current():
    """Месячная периодичность (по умолчанию) → числа как без параметра."""
    plain = run(_model())
    explicit = run(_model(profit_period="month", vat_period="month"))
    assert plain.cashflow["C12"] == explicit.cashflow["C12"]
    assert plain.balance["B21"] == explicit.balance["B21"]


def test_quarterly_profit_tax_shifts_payment_and_b21():
    """Квартальная уплата прибыли: C12-прибыль в мес.3/6/9/12, между — долг в B21."""
    monthly = run(_model())
    quarterly = run(_model(profit_period="quarter"))
    i27 = monthly.income["I27"]
    # начисление (I27) не изменилось
    assert quarterly.income["I27"] == i27
    # уплата прибыли сдвинута: разница C12 относительно помесячной
    dc = [quarterly.cashflow["C12"][t] - monthly.cashflow["C12"][t] for t in range(12)]
    for t in range(12):
        if t % 3 == 2:                                   # конец квартала — доплата накопленного
            assert dc[t] == sum(i27[t - 2:t + 1], Decimal(0)) - i27[t]
        else:                                            # внутри квартала — недоплата
            assert dc[t] == -i27[t]
    # B21 внутри квартала растёт, в конце обнуляется (относительно помесячной задолженности)
    assert quarterly.balance["B21"][0] == monthly.balance["B21"][0] + i27[0]
    assert quarterly.balance["B21"][2] == monthly.balance["B21"][2]


def test_yearly_vat_tail_in_b21():
    """Годовая уплата НДС на 14 мес.: уплата в мес.12, хвост 2 мес. — в B21."""
    monthly = run(_model(n=14, vat="0.20"))
    yearly = run(_model(n=14, vat="0.20", vat_period="year"))
    # начисление НДС (сумма к уплате) неизменно → годовая сумма C12 за 12 мес. совпадает
    assert almost_equal(sum(yearly.cashflow["C12"][:12], Decimal(0)),
                        sum(monthly.cashflow["C12"][:12], Decimal(0)))
    # хвост (мес.12,13) остаётся задолженностью → B21 в конце выше помесячной
    assert yearly.balance["B21"][13] > monthly.balance["B21"][13]


def test_invariant_with_periodicity():
    r = run(_model(n=18, vat="0.20", profit_period="quarter", vat_period="quarter"))
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))


def test_periodicity_with_auto_financing():
    """Автоподбор кредита видит сдвиг уплаты налога: расчёт сходится, инвариант держится."""
    m = _model(n=12, vat="0.20", profit_period="quarter")
    m.financing.auto_financing.enabled = True
    m.financing.auto_financing.annual_rate = Decimal("0.20")
    r = run(m)
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))
    assert "не сошёлся" not in " ".join(r.warnings)


def test_accrual_unchanged_profit_and_net_income():
    """Периодичность — чисто кассовая: I26/I27/I28 не меняются."""
    monthly = run(_model(vat="0.20"))
    shifted = run(_model(vat="0.20", profit_period="year", vat_period="quarter"))
    assert monthly.income["I27"] == shifted.income["I27"]
    assert monthly.income["I28"] == shifted.income["I28"]
    assert monthly.income["I26"] == shifted.income["I26"]
