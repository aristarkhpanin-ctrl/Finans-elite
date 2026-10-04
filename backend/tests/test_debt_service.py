"""Взгляд банка: покрытие долга и долговая нагрузка (0.9.58, пакет L, L1).

Блок только читает отчёты, поэтому проверяется тождествами с кассой: что вошло в поток
для обслуживания долга и что — в сами платежи, должно сходиться с ``C13``/``C23``/``C24``/
``C25`` до копейки. Отдельно — то, что легко перепутать: финансовый лизинг — платёж по
долгу, операционный — издержка; погашение автокредита — не плановый платёж.
"""
from __future__ import annotations

from decimal import Decimal

from calc_core import run
from calc_core.engine.pipeline import finance_lease_payments, scheduled_loan_principal
from calc_core.models.financing import Lease, Loan
from calc_core.models.investment import Asset
from calc_core.money import ZERO
from calc_core.reports.debt import BANK_DSCR_MIN, BANK_LEVERAGE_MAX
from calc_core.samples import build_sample_project, build_services_project

EPS = Decimal("0.01")


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) < EPS


def _no_loans():
    m = build_sample_project()
    m.financing.loans = []
    return m


def test_no_debt_no_block():
    """Нет займов, лизинга и долга на балансе — блока нет, а не таблица нулей."""
    assert run(build_services_project()).debt_service is None
    assert run(_no_loans()).debt_service is None


def test_a_plain_loan_is_interest_plus_principal_against_operating_flow():
    r = run(build_sample_project())
    y = r.debt_service.years[0]
    c = r.cashflow
    assert _close(y.interest, sum(c["C24"], ZERO))
    assert _close(y.principal, sum(c["C23"], ZERO))
    assert _close(y.service, y.interest + y.principal)
    # Ни лизинга, ни депозитов: поток для обслуживания долга — ровно операционный.
    assert _close(y.cfads, sum(c["C13"], ZERO))
    assert y.dscr == y.cfads / y.service
    # Покрытие ниже единицы — назван недостаток: сколько платить из других денег.
    assert y.dscr < 1 and _close(y.shortfall, y.service - y.cfads)
    assert r.debt_service.min_dscr == y.dscr and r.debt_service.min_dscr_year == "Год 1"


def test_finance_lease_is_debt_service_operating_lease_is_a_cost():
    """Финансовый лизинг — покупка в долг: его платёж — платёж по долгу. Операционный —
    аренда: он уменьшает поток, а долгом не становится. Страхование — издержка при любом."""
    op = _no_loans()
    op.financing.leases = [Lease(name="Аренда", monthly_payment=Decimal("1000"),
                                 term_months=12, insurance_monthly=Decimal("50"))]
    assert run(op).debt_service is None             # аренда — не долг

    fin = _no_loans()
    fin.financing.leases = [Lease(name="Пресс", monthly_payment=Decimal("1000"),
                                  term_months=12, finance=True, annual_rate=Decimal("0.12"),
                                  insurance_monthly=Decimal("50"))]
    r = run(fin)
    y = r.debt_service.years[0]
    assert _close(y.lease, Decimal("12000")) and y.interest == ZERO and y.principal == ZERO
    # Страхование (600) — издержка: из потока вычтено, в платежи не вошло.
    c = r.cashflow
    assert _close(y.cfads, sum(c["C13"], ZERO) - Decimal("600"))
    # Части C25 сходятся: платежи финансового лизинга + операционная часть = C25.
    pay = finance_lease_payments(fin, fin.n)
    assert all(_close(c["C25"][t], pay[t] + Decimal("50")) for t in range(fin.n))


def test_autocredit_principal_is_not_a_scheduled_payment():
    """Автокредит гасится из свободных денег — это не плановый платёж. Его проценты
    входят в обслуживание, тело — нет, и оговорка это называет."""
    m = build_sample_project()
    m.investment_plan.assets.append(
        Asset(name="Линия", cost=Decimal("100000"), purchase_month=1, life_months=60))
    m.financing.auto_financing.enabled = True
    r = run(m)
    c = r.cashflow
    planned = scheduled_loan_principal(m, m.n)
    assert sum(c["C23"], ZERO) > sum(planned, ZERO) + EPS     # автокредит гасился
    y = r.debt_service.years[0]
    assert _close(y.principal, sum(planned, ZERO))
    assert _close(y.interest, sum(c["C24"], ZERO))             # проценты — все
    assert "автокредита" in r.debt_service.note


def test_foreign_loan_principal_is_in_rubles_by_the_rate():
    """Валютный заём: плановое тело — в рублях по курсу, ровно как в C23."""
    m = build_sample_project()
    m.financing.loans = [Loan(name="EUR", amount=Decimal("1000"), term_months=6,
                              foreign=True)]
    m.environment.fx_open = Decimal("100")
    m.environment.fx_rate = [Decimal(100 + 2 * t) for t in range(m.n)]
    r = run(m)
    assert all(_close(a, b) for a, b in zip(r.cashflow["C23"],
                                            scheduled_loan_principal(m, m.n), strict=True))
    assert _close(r.debt_service.years[0].principal, sum(r.cashflow["C23"], ZERO))


def test_years_without_payments_and_partial_years_are_named_not_zero():
    """Год без платежей — «долга нет» (None), а не бесконечное или нулевое покрытие;
    неполный год годовой EBITDA не имеет — нагрузка не считается, и сказано почему."""
    m = build_sample_project()
    m.header.duration_months = 18
    # Платежи — с месяца после получения по срок: заём на 6 месяцев гасится в первый год
    # (на 12 месяцев последний платёж пришёлся бы на 13-й месяц, во второй год).
    m.financing.loans[0].term_months = 6
    r = run(m)
    first, second = r.debt_service.years
    assert first.months == 12 and second.months == 6 and second.label == "Год 2"
    assert second.dscr is None and second.shortfall == ZERO
    assert second.leverage is None and "неполный год" in second.leverage_note
    assert r.debt_service.min_dscr_year == "Год 1"


def test_capex_in_debt_service_years_is_named():
    """Вложения в годы платежей из потока не вычитаются — и это напечатано: банк,
    вычитающий поддерживающие вложения, увидит покрытие ниже."""
    r = run(build_sample_project())                  # станок покупается в «Год 1»
    assert "Капитальные вложения из потока не вычитаются" in r.debt_service.note
    assert "Год 1" in r.debt_service.note


def test_the_bank_thresholds_are_named_as_practice_not_law():
    note = run(build_sample_project()).debt_service.note
    assert "практика, а не норма закона" in note
    assert BANK_DSCR_MIN == Decimal("1.2") and BANK_LEVERAGE_MAX == Decimal("4")
    assert "1,2" in note and "4 годовых EBITDA" in note


def test_net_debt_and_ebitda_are_read_from_the_statements():
    r = run(build_sample_project())
    y = r.debt_service.years[0]
    b, i = r.balance, r.income
    assert _close(y.net_debt, b["B22"][11] + b["B26"][11] - b["B1"][11] - b["B6"][11])
    assert _close(y.ebitda, sum(i["I23"], ZERO) + sum(i["I18"], ZERO) + sum(i["I17"], ZERO))
    # Денег больше долга — чистого долга нет, и отношение не считается с причиной.
    assert y.net_debt < 0 and y.leverage is None and y.leverage_note == "чистого долга нет"
