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
    Loan,
    OperatingPlan,
    PaymentTerms,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.models.common import RepaymentType

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


def _loan_model(loan: Loan, fx_open: str, fx_rate, n: int) -> ProjectModel:
    return ProjectModel(
        header=ProjectHeader(name="loan-fx", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        environment=Environment(fx_open=D(fx_open), fx_rate=[D(x) for x in fx_rate]),
        financing=Financing(loans=[loan], common_shares=D(100)),
    )


def test_foreign_loan_revaluation_is_a_loss_when_rate_rises():
    """Валютный заём 100 ед.: курс 60→70 → долг в основной валюте растёт 6000→7000,
    курсовая разница −1000 (убыток), баланс сходится."""
    loan = Loan(name="Валютный", amount=D(100), start_month=0, term_months=12,
                annual_rate=D("0"), repayment=RepaymentType.BULLET, foreign=True)
    r = run(_loan_model(loan, fx_open="60", fx_rate=["60", "70"], n=2))
    assert r.cashflow["C22"] == [D(6000), D(0)]       # поступление 100×60
    assert r.balance["B26"] == [D(6000), D(7000)]     # долг переоценён по курсу
    assert r.income["I25"] == [D(0), D(-1000)]        # курсовой убыток на остаток
    assert r.balance["B1"] == [D(6000), D(6000)]      # деньги не двигались
    assert _balanced(r)


def test_foreign_loan_at_unit_fx_equals_base_loan():
    """Валютный заём при курсе ≡1 тождественен обычному займу (проверка машинерии)."""
    n = 6
    common = dict(amount=D(50000), start_month=0, term_months=6, annual_rate=D("0.15"))
    rf = run(_loan_model(Loan(name="f", foreign=True, **common), "1", ["1"] * n, n))
    rb = run(_loan_model(Loan(name="b", foreign=False, **common), "1", ["1"] * n, n))
    for line in ("I18", "I25"):
        assert rf.income[line] == rb.income[line]
    assert rf.balance["B26"] == rb.balance["B26"]
    assert rf.cashflow["C24"] == rb.cashflow["C24"]   # проценты одинаковы


def test_foreign_sales_receivable_revalues_on_collection():
    """Экспорт 100 ед. в кредит: отгрузка по курсу 60 (выручка 6000), оплата по курсу 70
    (деньги 7000); разница 1000 — курсовой доход на дебиторку. Баланс сходится."""
    n = 2
    m = ProjectModel(
        header=ProjectHeader(name="export", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        environment=Environment(fx_open=D("60"), fx_rate=[D("60"), D("70")]),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Экспортный товар")],
            sales=[SalesLine(product_id="p1", volume=[D(100), D(0)], price=[D(1), D(1)],
                             payment=PaymentTerms(payment_delay_months=1), foreign=True)],
        ),
        financing=Financing(common_shares=D(100)),
    )
    r = run(m)
    assert r.income["I1"] == [D(6000), D(0)]       # выручка по курсу отгрузки 60
    assert r.cashflow["C1"] == [D(0), D(7000)]     # деньги по курсу получения 70
    assert r.balance["B2"] == [D(6000), D(0)]      # дебиторка по курсу на конец периода
    assert r.income["I25"] == [D(0), D(1000)]      # курсовой доход на дебиторку при оплате
    assert r.balance["B32"] == [D(6000), D(7000)]  # прибыль = выручка + курсовая разница
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
