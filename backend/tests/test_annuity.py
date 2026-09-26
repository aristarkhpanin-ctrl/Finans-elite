"""Аннуитетный график займа (SPEC §10).

Банковский аннуитет — самый частый в жизни график: платёж постоянен, внутри него доля
процентов падает, доля тела растёт. До 0.9.41 движок знал только «равными долями тела» и
«в конце срока», и отраслевым шаблонам приходилось **называть это допущением** вместо
того, чтобы посчитать.

Проверяется не «код отработал», а четыре свойства графика, которые и делают его
аннуитетом; плюс два места, где он встречается с остальной методикой (валюта и
нормирование процентов), и один отказ — нулевая ставка не должна ломать формулу.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.engine.pipeline import _annuity_payment, _loan_schedule
from calc_core.models import (
    Company,
    Environment,
    Financing,
    Loan,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.models.common import RepaymentType
from calc_core.money import quantize

D = Decimal
EPS = D("0.01")


def _loan(**kw) -> Loan:
    base = dict(name="Кредит", amount=D(1200000), start_month=0, term_months=24,
                annual_rate=D("0.18"), repayment=RepaymentType.ANNUITY)
    base.update(kw)
    return Loan(**base)


def _model(loans, n=36, **settings) -> ProjectModel:
    opts = dict(discount_rate_annual=D("0.15"), profit_tax_rate=D("0.20"),
                property_tax_rate=D("0"), vat_rate=D("0"))
    opts.update(settings)
    return ProjectModel(
        header=ProjectHeader(name="Аннуитет", start_date=date(2026, 1, 1),
                             duration_months=n),
        settings=ProjectSettings(**opts),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(400)] * n, price=[D(1000)] * n)],
        ),
        financing=Financing(loans=loans, common_shares=D(100)),
    )


# --- Свойства самого графика ---

def test_the_payment_is_constant_and_that_is_the_whole_point():
    """Платёж «проценты + тело» один и тот же во всех месяцах, кроме последнего.

    Последний закрывает остаток: аннуитет — бесконечная дробь, и хвост округления обязан
    куда-то деться. Отклонение последнего платежа — копейки, а не другой платёж.
    """
    loan = _loan()
    _, principal, interest = _loan_schedule(loan, 30)
    pays = [principal[t] + interest[t] for t in range(1, 25)]

    assert all(abs(p - pays[0]) < EPS for p in pays[:-1]), "платёж перестал быть равным"
    assert abs(pays[-1] - pays[0]) < D("1"), "последний платёж ушёл дальше округления"
    # Формула и график говорят одно и то же.
    assert abs(pays[0] - _annuity_payment(loan.amount, loan.monthly_rate(), 24)) < EPS


def test_the_body_is_repaid_exactly_and_the_debt_reaches_zero():
    """Сумма тела = сумме займа **до копейки**, иначе `B26` никогда не обнулится."""
    loan = _loan()
    _, principal, _ = _loan_schedule(loan, 30)
    assert quantize(sum(principal)) == quantize(loan.amount)
    # И после срока не остаётся ни платежей, ни процентов.
    assert sum(principal[25:]) == 0
    assert all(i == 0 for i in _loan_schedule(loan, 30)[2][25:])


def test_inside_the_payment_interest_falls_and_the_body_grows():
    """То, ради чего аннуитет и отличают от «равных долей»: в начале платишь банку, в
    конце — себе. Модель, где это перепутано, врёт о свободных деньгах первого года."""
    _, principal, interest = _loan_schedule(_loan(), 30)
    body = [principal[t] for t in range(1, 25)]
    paid = [interest[t] for t in range(1, 25)]

    assert all(body[i] < body[i + 1] for i in range(len(body) - 2))
    assert all(paid[i] > paid[i + 1] for i in range(len(paid) - 1))
    assert paid[0] > paid[-1] * 10          # первый месяц против последнего


def test_the_annuity_costs_more_than_equal_principal_over_the_term():
    """Равный платёж достигается тем, что тело гасится медленнее, — и процентов выходит
    больше. Если бы вышло меньше, аннуитет был бы бесплатным обедом."""
    _, _, ann = _loan_schedule(_loan(), 30)
    _, _, equal = _loan_schedule(_loan(repayment=RepaymentType.EQUAL_PRINCIPAL), 30)
    _, _, bullet = _loan_schedule(_loan(repayment=RepaymentType.BULLET), 30)
    assert sum(equal) < sum(ann) < sum(bullet)


def test_a_zero_rate_annuity_is_exactly_equal_principal():
    """Ноль в знаменателе формулы — не предел, а отдельная ветка: «почти ноль» дал бы
    платёж в миллиарды. При нулевой ставке график обязан совпасть с равными долями."""
    zero = dict(annual_rate=D("0"))
    ann = _loan_schedule(_loan(**zero), 30)
    equal = _loan_schedule(_loan(repayment=RepaymentType.EQUAL_PRINCIPAL, **zero), 30)
    assert ann == equal


def test_a_term_of_zero_does_not_divide_by_zero_and_leaves_no_phantom_debt():
    """Нулевой срок — это опечатка ввода, и формула на ней делит на ноль.

    Из двух возможных реакций выбрана та, что не оставляет следов: заём приходит и тут же
    возвращается (как «в конце срока» с нулевым сроком), долг обнуляется. Второй вариант —
    «платежей нет вовсе» — оставил бы вечный остаток в `B26`, молча начисляющий проценты
    до конца горизонта: опечатка, которая выглядит как финансирование.
    """
    proceeds, principal, interest = _loan_schedule(_loan(term_months=0), 12)
    assert sum(principal) == sum(proceeds)      # пришло и ушло, долга не осталось
    assert sum(interest) == 0
    assert _annuity_payment(D(1000), D("0.01"), 0) == 0


def test_a_later_start_moves_the_whole_schedule():
    """Месяц получения сдвигает график целиком, а не обрезает его: проценты начинаются
    после получения, платежи — со следующего месяца."""
    _, principal, interest = _loan_schedule(_loan(start_month=6), 40)
    assert interest[6] == 0 and principal[6] == 0          # в месяц получения платежа нет
    assert interest[7] > 0 and principal[7] > 0
    assert quantize(sum(principal)) == quantize(D(1200000))


# --- Встреча с остальной методикой ---

def test_the_balance_still_converges():
    """Единственная проверка, которую нельзя пропустить ни в одной правке движка."""
    r = run(_model([_loan()]))
    assert [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]
    assert quantize(r.balance["B26"][-1]) == 0              # долг погашен к концу


def test_the_reports_see_the_same_payments_as_the_schedule():
    """C23 (тело) и C24 (проценты) — тот же график, а не второй его расчёт."""
    loan = _loan()
    r = run(_model([loan]))
    _, principal, interest = _loan_schedule(loan, 36)
    assert [quantize(v) for v in r.cashflow["C23"]] == [quantize(v) for v in principal]
    assert [quantize(v) for v in r.cashflow["C24"]] == [quantize(v) for v in interest]


def test_a_foreign_annuity_is_converted_not_recomputed():
    """Валютный заём считается в валюте и пересчитывается по курсу: аннуитет постоянен
    **в валюте займа**, а в рублях гуляет вместе с курсом — и это правда о займе."""
    loan = _loan(amount=D(20000), foreign=True, term_months=12)
    n = 24
    model = _model([loan], n=n)
    model.environment = Environment(fx_open=D(90), fx_rate=[D(90) + D(t) for t in range(n)])
    r = run(model)

    _, principal_f, interest_f = _loan_schedule(loan, n)
    fx = [D(90) + D(t) for t in range(n)]
    assert [quantize(v) for v in r.cashflow["C23"]] == [
        quantize(principal_f[t] * fx[t]) for t in range(n)]
    # В рублях платежи растут вместе с курсом — постоянными они быть и не должны.
    rub = [r.cashflow["C23"][t] + r.cashflow["C24"][t] for t in range(1, 13)]
    assert rub[-1] > rub[0]


def test_interest_normalisation_splits_the_annuity_interest():
    """Норматив ЦБ (SPEC §11) делит **процентную** часть платежа, а не платёж целиком:
    тело займа издержкой не является ни при какой ставке."""
    loan = _loan(annual_rate=D("0.30"))
    r = run(_model([loan], cb_refinancing_rate=D("0.10"), interest_norm_multiple=D("1")))
    _, principal, interest = _loan_schedule(loan, 36)

    # Весь процент разошёлся по двум строкам, тело в них не попало.
    total = [r.income["I18"][t] + r.income["I24"][t] for t in range(36)]
    assert [quantize(v) for v in total] == [quantize(v) for v in interest]
    assert sum(r.income["I24"]) > 0                        # сверхнорматив есть
    assert quantize(sum(r.cashflow["C23"])) == quantize(loan.amount)
    assert quantize(sum(principal)) == quantize(loan.amount)


def test_interest_on_profit_keeps_the_whole_annuity_interest_out_of_i18():
    """Флаг «проценты из прибыли» сильнее норматива — и с аннуитетом ведёт себя так же."""
    r = run(_model([_loan(interest_on_profit=True)]))
    assert sum(r.income["I18"]) == 0
    assert sum(r.income["I24"]) > 0
