"""Конвейер расчёта (см. CALC-ENGINE-SPEC.md §4).

Реализован согласованный (балансирующийся) срез функционала:
сбыт и издержки с **условиями оплаты** (разрыв accrual/cash → дебиторка/кредиторка/
авансы, §5.1a), амортизация, налог на прибыль и имущество, займы (проценты + тело),
акционерный капитал, дивиденды.

Запасы и НДС добавляются следующими под-частями 5.1 — каждый раз с сохранением
балансового инварианта B20 = B34.
"""
from __future__ import annotations

from decimal import Decimal

from ..models import CostFunction, DirectCostKind, ProjectModel, RepaymentType
from ..money import D, ZERO
from ..series import add, cumulative, zeros
from ..reports.statements import (
    build_balance,
    build_cashflow,
    build_income,
    build_profit_use,
)
from .errors import ModelError
from .timing import cost_timing, sales_timing

# Функции издержек, попадающие в «Общие издержки» (C5) и «Затраты на персонал» (C6).
_STAFF_FUNCTIONS = {
    CostFunction.STAFF_ADMIN,
    CostFunction.STAFF_PRODUCTION,
    CostFunction.STAFF_MARKETING,
}


def _pad(values: list[Decimal], n: int) -> list[Decimal]:
    out = zeros(n)
    for i, v in enumerate(values):
        if i >= n:
            break
        out[i] = D(v)
    return out


def _sales(model: ProjectModel, n: int):
    """Сбыт → (I1 начисление, C1 деньги, B2 дебиторка, B24 авансы)."""
    i1 = zeros(n)
    c1 = zeros(n)
    b2 = zeros(n)
    b24 = zeros(n)
    for line in model.operating_plan.sales:
        vol = _pad(line.volume, n)
        price = _pad(line.price, n)
        revenue = [vol[t] * price[t] for t in range(n)]
        cash, recv, adv = sales_timing(revenue, line.payment, n)
        i1 = add(i1, revenue)
        c1 = add(c1, cash)
        b2 = add(b2, recv)
        b24 = add(b24, adv)
    return i1, c1, b2, b24


def _direct(model: ProjectModel, n: int):
    """Прямые издержки → (I5, I6 начисление; C2, C3 деньги; кредиторка)."""
    i5 = zeros(n)
    i6 = zeros(n)
    c2 = zeros(n)
    c3 = zeros(n)
    payables = zeros(n)
    for line in model.operating_plan.direct_costs:
        amt = _pad(line.amount, n)
        cash, pay = cost_timing(amt, line.payment_delay_months, n)
        payables = add(payables, pay)
        if line.kind == DirectCostKind.MATERIALS:
            i5 = add(i5, amt)
            c2 = add(c2, cash)
        else:
            i6 = add(i6, amt)
            c3 = add(c3, cash)
    return i5, i6, c2, c3, payables


def _fixed(model: ProjectModel, n: int):
    """Постоянные издержки → (группы начисления I10–I15; C5, C6 деньги; кредиторка)."""
    groups = {fn: zeros(n) for fn in CostFunction}
    c5 = zeros(n)  # общие издержки
    c6 = zeros(n)  # затраты на персонал
    payables = zeros(n)
    for line in model.operating_plan.fixed_costs:
        amt = _pad(line.amount, n)
        cash, pay = cost_timing(amt, line.payment_delay_months, n)
        groups[line.function] = add(groups[line.function], amt)
        payables = add(payables, pay)
        if line.function in _STAFF_FUNCTIONS:
            c6 = add(c6, cash)
        else:
            c5 = add(c5, cash)
    return groups, c5, c6, payables


def _assets(model: ProjectModel, n: int):
    """Активы → (capex по месяцам, амортизация по месяцам)."""
    capex = zeros(n)
    dep = zeros(n)
    for asset in model.investment_plan.assets:
        p = asset.purchase_month
        if 0 <= p < n:
            capex[p] += asset.cost
        d = asset.monthly_depreciation()
        for t in range(p, min(p + asset.life_months, n)):
            if t >= 0:
                dep[t] += d
    return capex, dep


def _loan_schedule(loan, n: int):
    """График займа → (поступления, погашение тела, проценты), помесячно."""
    proceeds = zeros(n)
    principal = zeros(n)
    interest = zeros(n)
    m = loan.monthly_rate()
    s = loan.start_month
    term = loan.term_months
    bal = ZERO
    per = loan.amount / Decimal(term) if term > 0 else loan.amount
    for t in range(n):
        interest[t] = bal * m  # проценты на остаток на начало месяца
        if t == s:
            bal += loan.amount
            proceeds[t] = loan.amount
        due = ZERO
        if loan.repayment == RepaymentType.EQUAL_PRINCIPAL:
            if s < t <= s + term:
                due = per
        else:  # BULLET — весь возврат в конце срока
            if t == s + term:
                due = bal
        pay = min(due, bal)
        principal[t] = pay
        bal -= pay
    return proceeds, principal, interest


def _equity(model: ProjectModel, n: int) -> list[Decimal]:
    eq = zeros(n)
    for inj in model.financing.equity:
        if 0 <= inj.month < n:
            eq[inj.month] += inj.amount
    return eq


def run_pipeline(model: ProjectModel):
    """Выполнить расчёт и вернуть (income, cashflow, balance, profit_use) Statement-ы."""
    n = model.n
    sb = model.company.starting_balance

    # Проверка сходимости стартового баланса (SPEC §16).
    if abs(sb.assets() - sb.liabilities_equity()) > Decimal("0.01"):
        raise ModelError(
            f"Стартовый баланс не сходится: актив {sb.assets()} != пассив "
            f"{sb.liabilities_equity()}"
        )

    settings = model.settings

    # --- операционный контур (accrual + cash + оборотный капитал) ---
    i1, c1, b2, b24 = _sales(model, n)
    i5, i6, c2, c3, pay_direct = _direct(model, n)
    fixed, c5, c6, pay_fixed = _fixed(model, n)
    b23 = add(pay_direct, pay_fixed)

    # --- инвестиции и амортизация ---
    capex, dep = _assets(model, n)
    b9 = [sb.fixed_assets_net + c for c in cumulative(capex)]
    b10 = list(cumulative(dep))
    b11 = [b9[t] - b10[t] for t in range(n)]

    # Налог на имущество (база — остаточная стоимость, годовая ставка → помесячно)
    prop_monthly = settings.property_tax_rate / Decimal(12)
    i9 = [prop_monthly * b11[t] for t in range(n)]

    # --- займы ---
    loan_proceeds = zeros(n)
    loan_principal = zeros(n)
    loan_interest = zeros(n)
    for loan in model.financing.loans:
        pr, pp, ii = _loan_schedule(loan, n)
        loan_proceeds = add(loan_proceeds, pr)
        loan_principal = add(loan_principal, pp)
        loan_interest = add(loan_interest, ii)

    equity_in = _equity(model, n)
    dividends = _pad(model.financing.dividends, n)

    # --- Отчёт о прибылях и убытках (начисление) ---
    income_leaves = {
        "I1": i1,
        "I5": i5,
        "I6": i6,
        "I9": i9,
        "I10": fixed[CostFunction.ADMIN],
        "I11": fixed[CostFunction.PRODUCTION],
        "I12": fixed[CostFunction.MARKETING],
        "I13": fixed[CostFunction.STAFF_ADMIN],
        "I14": fixed[CostFunction.STAFF_PRODUCTION],
        "I15": fixed[CostFunction.STAFF_MARKETING],
        "I17": dep,
        "I18": loan_interest,
    }
    income = build_income(income_leaves, n, settings.profit_tax_rate)

    # --- Использование прибыли (нераспределённая прибыль = B32) ---
    profit_use = build_profit_use(
        net_profit=income["I28"],
        dividends=dividends,
        reserves=zeros(n),
        opening_retained=sb.retained_earnings,
        n=n,
    )
    retained = profit_use["P7"]

    # --- Кэш-фло (оплата) ---
    c28 = zeros(n)
    if n > 0:
        c28[0] = sb.cash
    taxes_cash = add(income["I27"], i9)  # налог на прибыль + имущество (v0: оплата в периоде)
    cashflow_leaves = {
        "C1": c1,
        "C2": c2,
        "C3": c3,
        "C5": c5,
        "C6": c6,
        "C12": taxes_cash,
        "C14": capex,
        "C21": equity_in,
        "C22": loan_proceeds,
        "C23": loan_principal,
        "C24": loan_interest,
        "C26": dividends,
        "C28": c28,
    }
    cashflow = build_cashflow(cashflow_leaves, n)

    # --- Баланс ---
    paid_in = [sb.paid_in_capital + e for e in cumulative(equity_in)]
    debt = [sb.debt + cumulative(loan_proceeds)[t] - cumulative(loan_principal)[t] for t in range(n)]
    balance_leaves = {
        "B1": cashflow["C29"],     # денежные средства = сальдо Кэш-фло
        "B2": b2,                  # счета к получению (дебиторка)
        "B9": b9,
        "B10": b10,
        "B14": b11,                # остаточная стоимость → оборудование (v0)
        "B23": b23,                # счета к оплате (кредиторка)
        "B24": b24,                # полученные авансы
        "B26": debt,               # долгосрочные займы
        "B27": paid_in,            # обыкновенные акции
        "B32": retained,           # нераспределённая прибыль
    }
    balance = build_balance(balance_leaves, n)

    return income, cashflow, balance, profit_use
