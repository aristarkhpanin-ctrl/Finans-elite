"""Финансовый лизинг (SPEC §10): капитализация предмета (B19), тело → B26, проценты I18,
амортизация I17. Платёж = проценты + тело; баланс сходится. Числа выверены вручную.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.models import (
    Company,
    Financing,
    Lease,
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


def _model(n, leases):
    """Только лизинг; пустой стартовый баланс, без налогов (касса может уходить в минус)."""
    return ProjectModel(
        header=ProjectHeader(name="ls", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(),
        financing=Financing(leases=leases),
    )


def test_finance_lease_zero_rate():
    """Ставка 0: предмет = 2×1000 = 2000, амортизация 1000/мес, процентов нет.

    B19 (предмет) и B26 (обязательство) гасятся к концу срока; платёж → C25; I21 = 0.
    """
    n = 2
    lease = Lease(name="ФЛ", monthly_payment=D(1000), start_month=0, term_months=2,
                  finance=True, annual_rate=D("0"))
    r = run(_model(n, [lease]))
    assert [q(v) for v in r.balance["B19"]] == [D("1000.00"), D("0.00")]
    assert [q(v) for v in r.balance["B26"]] == [D("1000.00"), D("0.00")]
    assert [q(v) for v in r.income["I17"]] == [D("1000.00"), D("1000.00")]
    assert all(v == 0 for v in r.income["I18"])
    assert [q(v) for v in r.cashflow["C25"]] == [D("1000.00"), D("1000.00")]
    assert all(v == 0 for v in r.income["I21"])     # не операционный лизинг
    assert _balanced(r)


def test_finance_lease_interest_principal_split():
    """Ставка > 0: проценты на остаток обязательства убывают, тело гасит долг к концу срока."""
    n = 3
    lease = Lease(name="ФЛ", monthly_payment=D(1000), start_month=0, term_months=3,
                  finance=True, annual_rate=D("0.20"))
    r = run(_model(n, [lease]))
    # к концу срока предмет полностью амортизирован, обязательство погашено
    assert q(r.balance["B19"][2]) == D("0.00")
    assert q(r.balance["B26"][2]) == D("0.00")
    # суммарная издержка (амортизация + проценты) = суммарный отток платежей
    assert q(sum(r.income["I17"]) + sum(r.income["I18"])) == q(sum(r.cashflow["C25"]))
    # проценты начисляются на убывающий остаток: убывают и положительны
    assert r.income["I18"][0] > r.income["I18"][1] > r.income["I18"][2] > 0
    assert _balanced(r)


def test_operational_lease_unchanged():
    """Операционный лизинг (по умолчанию): платёж целиком в I21 и C25, B19 = 0."""
    n = 2
    lease = Lease(name="ОЛ", monthly_payment=D(500), start_month=0, term_months=2)
    r = run(_model(n, [lease]))
    assert [q(v) for v in r.income["I21"]] == [D("500.00"), D("500.00")]
    assert all(v == 0 for v in r.balance["B19"])
    assert [q(v) for v in r.cashflow["C25"]] == [D("500.00"), D("500.00")]
    assert _balanced(r)


def test_operational_lease_with_insurance():
    """Операционный лизинг + страхование: I21 = платёж + страховка, C25 = то же; баланс сходится."""
    n = 2
    lease = Lease(name="ОЛ", monthly_payment=D(500), start_month=0, term_months=2,
                  insurance_monthly=D(50))
    r = run(_model(n, [lease]))
    assert [q(v) for v in r.income["I21"]] == [D("550.00"), D("550.00")]
    assert [q(v) for v in r.cashflow["C25"]] == [D("550.00"), D("550.00")]
    assert _balanced(r)


def test_finance_lease_with_insurance():
    """Финансовый лизинг + страхование: страховка — единственная составляющая I21; C25 =
    платёж + страховка; предмет амортизируется как обычно; баланс сходится."""
    n = 2
    lease = Lease(name="ФЛ", monthly_payment=D(1000), start_month=0, term_months=2,
                  finance=True, annual_rate=D("0"), insurance_monthly=D(50))
    r = run(_model(n, [lease]))
    assert [q(v) for v in r.income["I21"]] == [D("50.00"), D("50.00")]        # только страховка
    assert [q(v) for v in r.cashflow["C25"]] == [D("1050.00"), D("1050.00")]  # платёж + страховка
    assert [q(v) for v in r.balance["B19"]] == [D("1000.00"), D("0.00")]      # предмет амортизируется
    assert _balanced(r)


def test_finance_lease_buyout_capitalizes_and_depreciates():
    """Выкуп по окончании лизинга: предмет становится собственным ОС (оборудование B14) в
    месяц start+term (оплата — приобретение активов C14) и амортизируется за срок службы
    после выкупа (I17). Баланс сходится.
    """
    n = 4
    lease = Lease(name="ФЛ", monthly_payment=D(1000), start_month=0, term_months=2,
                  finance=True, annual_rate=D("0"), buyout_price=D(600), buyout_life_months=2)
    r = run(_model(n, [lease]))
    # выкуп в мес. 2: приобретение ОС 600 (C14), затем амортизация 300/мес (мес. 2, 3)
    assert [q(v) for v in r.cashflow["C14"]] == [D("0.00"), D("0.00"), D("600.00"), D("0.00")]
    assert [q(v) for v in r.balance["B14"]] == [D("0.00"), D("0.00"), D("300.00"), D("0.00")]
    # I17: амортизация предмета лизинга (мес. 0,1 = 1000) + выкупного ОС (мес. 2,3 = 300)
    assert [q(v) for v in r.income["I17"]] == [D("1000.00"), D("1000.00"), D("300.00"), D("300.00")]
    assert _balanced(r)


def test_operational_lease_buyout():
    """Выкуп операционного лизинга: после срока предмет капитализируется (B14) и
    амортизируется — операционный лизинг сам предмет не капитализировал (B19=0)."""
    n = 3
    lease = Lease(name="ОЛ", monthly_payment=D(500), start_month=0, term_months=1,
                  buyout_price=D(400), buyout_life_months=2)
    r = run(_model(n, [lease]))
    assert all(v == 0 for v in r.balance["B19"])                         # операционный: предмет не на балансе
    assert [q(v) for v in r.cashflow["C14"]] == [D("0.00"), D("400.00"), D("0.00")]
    assert [q(v) for v in r.balance["B14"]] == [D("0.00"), D("200.00"), D("0.00")]  # 400, аморт. 200/мес
    assert _balanced(r)
