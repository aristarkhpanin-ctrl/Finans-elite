"""Проводка I24 — «издержки, отнесённые на прибыль» (SPEC §12, §22.1).

Невычитаемые издержки (общие издержки «из прибыли» и проценты «на прибыль»):
- НЕ входят в I23 и НЕ уменьшают налоговую базу I26 (→ налог выше);
- уменьшают чистую прибыль I28 (реальная издержка);
- реально оплачиваются (деньги уходят), балансовый инвариант сохраняется.

Часть проверок — ручные (числа выведены на бумаге), часть — относительные
(сравнение с базовым прогоном), чтобы не привязываться к «некрасивым» суммам процентов.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Company,
    Financing,
    FixedCostLine,
    Loan,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.models.common import CostFunction, RepaymentType

D = Decimal


def _balanced(r) -> bool:
    """Баланс сходится с точностью до копеек (контракт ядра — допуск ε=0.01)."""
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def _base_model(fixed_costs=None, loans=None) -> ProjectModel:
    """1 месяц: выручка 1000 ₽ наличными, без НДС, налог на прибыль 20%."""
    n = 1
    return ProjectModel(
        header=ProjectHeader(name="I24", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(
            discount_rate_annual=D("0"),
            profit_tax_rate=D("0.20"),
            property_tax_rate=D("0"),
            vat_rate=D("0"),
        ),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(10)], price=[D(100)])],
            fixed_costs=fixed_costs or [],
        ),
        financing=Financing(loans=loans or [], common_shares=D(100)),
    )


def test_from_profit_overhead_increases_tax_and_reduces_net():
    """Издержка 100 «из прибыли»: прибыль до налога 1000, налог 200, чистая 700.

    Сравнение с обычной издержкой 100: та уменьшила бы базу (налог 180, чистая 720).
    «Из прибыли» — невычитаемая: лишние 20 налога — цена невычитаемости.
    """
    overhead = FixedCostLine(
        name="Штраф из прибыли", function=CostFunction.ADMIN,
        amount=[D(100)], from_profit=True,
    )
    r = run(_base_model(fixed_costs=[overhead]))

    assert r.income["I16"] == [D(0)]    # не попала в постоянные издержки
    assert r.income["I23"] == [D(1000)]  # прибыль до налога не уменьшена
    assert r.income["I24"] == [D(100)]   # отнесена на прибыль
    assert r.income["I26"] == [D(1000)]  # налоговая база НЕ уменьшена
    assert r.income["I27"] == [D(200)]   # налог 20% от 1000
    assert r.income["I28"] == [D(700)]   # чистая прибыль = 1000 − 100 − 200

    # Деньги: 1000 − 100 (издержка) − 200 (налог) = 700; баланс сходится.
    assert r.cashflow["C29"] == [D(700)]
    assert r.balance["B32"] == [D(700)]
    assert _balanced(r)


def test_normal_overhead_is_deductible_baseline():
    """Контроль: та же издержка 100 как обычная — уменьшает базу (налог 180, чистая 720)."""
    overhead = FixedCostLine(
        name="Аренда", function=CostFunction.ADMIN, amount=[D(100)],  # from_profit=False
    )
    r = run(_base_model(fixed_costs=[overhead]))
    assert r.income["I16"] == [D(100)]
    assert r.income["I24"] == [D(0)]
    assert r.income["I26"] == [D(900)]
    assert r.income["I27"] == [D(180)]
    assert r.income["I28"] == [D(720)]
    assert _balanced(r)


def _loan(on_profit: bool) -> Loan:
    return Loan(
        name="Заём", amount=D(100000), start_month=0, term_months=12,
        annual_rate=D("0.18"), repayment=RepaymentType.EQUAL_PRINCIPAL,
        interest_on_profit=on_profit,
    )


def test_interest_on_profit_routing_matches_baseline_interest():
    """Проценты «на прибыль» идут в I24 (не в I18), но денежная выплата та же.

    Относительная проверка: I24(on-profit) == I18(baseline); I18(on-profit) == 0;
    выплата процентов C24 одинакова; в обоих случаях баланс сходится.
    """
    n = 6
    base = _base_loan_model(_loan(on_profit=False), n)
    prof = _base_loan_model(_loan(on_profit=True), n)
    rb = run(base)
    rp = run(prof)

    assert rb.income["I24"] == [D(0)] * n          # базово процентов на прибыль нет
    assert rp.income["I18"] == [D(0)] * n          # на прибыль → I18 пуст
    assert rp.income["I24"] == rb.income["I18"]    # проценты переехали в I24
    assert rp.cashflow["C24"] == rb.cashflow["C24"]  # денежная выплата не изменилась
    # Баланс сходится в обоих режимах (run() проверяет инвариант).
    assert _balanced(rp)


def _base_loan_model(loan: Loan, n: int) -> ProjectModel:
    return ProjectModel(
        header=ProjectHeader(name="loan", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(
            discount_rate_annual=D("0"), profit_tax_rate=D("0.20"),
            property_tax_rate=D("0"), vat_rate=D("0"),
        ),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(50)] * n, price=[D(100)] * n)],
        ),
        financing=Financing(loans=[loan], common_shares=D(100)),
    )
