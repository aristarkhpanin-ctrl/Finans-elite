"""Тесты оборотного капитала (5.1a): дебиторка, кредиторка, авансы."""
from decimal import Decimal

from calc_core import run
from calc_core.engine.timing import cost_timing, sales_timing
from calc_core.models import PaymentTerms
from calc_core.samples import build_sample_project
from calc_core.series import cumulative, sub, add


def _terms(prepay="0", lead=0, delay=0):
    return PaymentTerms(
        prepayment_share=Decimal(prepay),
        advance_lead_months=lead,
        payment_delay_months=delay,
    )


def test_sales_delay_creates_receivable():
    # продажа 100 в t=1, отсрочка 1 мес → деньги в t=2, дебиторка на конец t=1
    cash, recv, adv = sales_timing([Decimal(0), Decimal(100), Decimal(0)], _terms(delay=1), 3)
    assert cash == [Decimal(0), Decimal(0), Decimal(100)]
    assert recv == [Decimal(0), Decimal(100), Decimal(0)]
    assert adv == [Decimal(0), Decimal(0), Decimal(0)]


def test_sales_prepayment_creates_advance():
    # 40% предоплата за 1 мес до поставки в t=1, остаток по факту
    cash, recv, adv = sales_timing([Decimal(0), Decimal(100), Decimal(0)], _terms("0.4", lead=1), 3)
    assert cash == [Decimal(40), Decimal(60), Decimal(0)]   # 40 предоплата в t=0, 60 в t=1
    assert adv == [Decimal(40), Decimal(0), Decimal(0)]     # аванс на конец t=0
    assert recv == [Decimal(0), Decimal(0), Decimal(0)]


def test_cost_delay_creates_payable():
    cash, pay = cost_timing([Decimal(100), Decimal(0), Decimal(0)], 1, 3)
    assert cash == [Decimal(0), Decimal(100), Decimal(0)]
    assert pay == [Decimal(100), Decimal(0), Decimal(0)]


def test_zero_terms_cash_equals_accrual():
    # без условий оплаты деньги совпадают с начислением (регрессия к v0)
    cash, recv, adv = sales_timing([Decimal(50), Decimal(70)], _terms(), 2)
    assert cash == [Decimal(50), Decimal(70)]
    assert recv == adv == [Decimal(0), Decimal(0)]


def test_accrual_cash_identity_on_sample():
    """cumulative(начисление) − cumulative(деньги) объясняется оборотным капиталом."""
    r = run(build_sample_project())
    n = r.n
    inc, cf, bal = r.income, r.cashflow, r.balance

    # Продажи: cum(I1) − cum(C1) == B2 − B24
    lhs = sub(cumulative(inc["I1"]), cumulative(cf["C1"]))
    rhs = sub(bal["B2"], bal["B24"])
    assert lhs == rhs

    # Издержки: cum(accrual) − cum(cash) == B23 (кредиторка)
    accrual = add(inc["I5"], inc["I6"], inc["I10"], inc["I11"], inc["I12"],
                  inc["I13"], inc["I14"], inc["I15"])
    cash = add(cf["C2"], cf["C3"], cf["C5"], cf["C6"])
    lhs2 = sub(cumulative(accrual), cumulative(cash))
    assert lhs2 == bal["B23"]


def test_sample_has_nonzero_working_capital():
    r = run(build_sample_project())
    # демо настроен с условиями оплаты — оборотный капитал должен появиться
    assert any(v != 0 for v in r.balance["B2"])
    assert any(v != 0 for v in r.balance["B23"])
    assert any(v != 0 for v in r.balance["B24"])
