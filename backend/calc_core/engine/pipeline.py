"""Конвейер расчёта v0 (см. CALC-ENGINE-SPEC.md §4).

Реализован согласованный (балансирующийся) срез функционала:
сбыт (оплата = начисление), прямые/постоянные издержки, амортизация, налог на прибыль
и имущество, займы (проценты + тело), акционерный капитал, дивиденды.

Эффекты оборотного капитала (дебиторка, запасы, НДС, авансы) и автоподбор добавляются
в следующих фазах — каждый раз с сохранением балансового инварианта B20 = B34.
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


def _pad(values: list[Decimal], n: int) -> list[Decimal]:
    out = zeros(n)
    for i, v in enumerate(values):
        if i >= n:
            break
        out[i] = D(v)
    return out


def _revenue(model: ProjectModel, n: int) -> list[Decimal]:
    """Выручка (без НДС) = Σ объём·цена по продуктам, помесячно."""
    rev = zeros(n)
    for line in model.operating_plan.sales:
        vol = _pad(line.volume, n)
        price = _pad(line.price, n)
        for t in range(n):
            rev[t] += vol[t] * price[t]
    return rev


def _direct_costs(model: ProjectModel, n: int) -> tuple[list[Decimal], list[Decimal]]:
    """Прямые издержки → (материалы I5, сдельная зарплата I6)."""
    materials = zeros(n)
    wages = zeros(n)
    for line in model.operating_plan.direct_costs:
        amt = _pad(line.amount, n)
        target = materials if line.kind == DirectCostKind.MATERIALS else wages
        for t in range(n):
            target[t] += amt[t]
    return materials, wages


def _fixed_costs(model: ProjectModel, n: int) -> dict[CostFunction, list[Decimal]]:
    """Постоянные издержки, сгруппированные по функции (строки I10–I15)."""
    groups = {fn: zeros(n) for fn in CostFunction}
    for line in model.operating_plan.fixed_costs:
        amt = _pad(line.amount, n)
        g = groups[line.function]
        for t in range(n):
            g[t] += amt[t]
    return groups


def _assets(model: ProjectModel, n: int) -> tuple[list[Decimal], list[Decimal]]:
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


def _loan_schedule(loan, n: int) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    """График займа → (поступления, погашение тела, проценты), помесячно."""
    proceeds = zeros(n)
    principal = zeros(n)
    interest = zeros(n)
    m = loan.monthly_rate()
    s = loan.start_month
    T = loan.term_months
    bal = ZERO
    if loan.repayment == RepaymentType.EQUAL_PRINCIPAL:
        per = loan.amount / Decimal(T) if T > 0 else loan.amount
    for t in range(n):
        interest[t] = bal * m                      # проценты на остаток на начало месяца
        if t == s:
            bal += loan.amount
            proceeds[t] = loan.amount
        # погашение тела
        due = ZERO
        if loan.repayment == RepaymentType.EQUAL_PRINCIPAL:
            if s < t <= s + T:
                due = per
        else:  # BULLET — весь возврат в конце срока
            if t == s + T:
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

    # --- производные ряды ---
    revenue = _revenue(model, n)
    materials, piece_wages = _direct_costs(model, n)
    fixed = _fixed_costs(model, n)
    capex, dep = _assets(model, n)

    # Основные средства: gross (B9), накопленная амортизация (B10), остаточная (B11=B14)
    b9 = [sb.fixed_assets_net + c for c in cumulative(capex)]
    b10 = list(cumulative(dep))
    b11 = [b9[t] - b10[t] for t in range(n)]

    # Налог на имущество (база — остаточная стоимость, годовая ставка → помесячно)
    prop_monthly = settings.property_tax_rate / Decimal(12)
    i9 = [prop_monthly * b11[t] for t in range(n)]

    # Займы (агрегировано по всем займам)
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

    # --- Отчёт о прибылях и убытках ---
    income_leaves = {
        "I1": revenue,
        "I5": materials,
        "I6": piece_wages,
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
    reserves = zeros(n)
    profit_use = build_profit_use(
        net_profit=income["I28"],
        dividends=dividends,
        reserves=reserves,
        opening_retained=sb.retained_earnings,
        n=n,
    )
    retained = profit_use["P7"]

    # --- Кэш-фло ---
    c28 = zeros(n)
    if n > 0:
        c28[0] = sb.cash  # опорное сальдо на начало
    taxes_cash = add(income["I27"], i9)  # налог на прибыль + имущество (v0: оплата в периоде)
    cashflow_leaves = {
        "C1": revenue,
        "C2": materials,
        "C3": piece_wages,
        "C5": add(fixed[CostFunction.ADMIN], fixed[CostFunction.PRODUCTION], fixed[CostFunction.MARKETING]),
        "C6": add(fixed[CostFunction.STAFF_ADMIN], fixed[CostFunction.STAFF_PRODUCTION], fixed[CostFunction.STAFF_MARKETING]),
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
        "B9": b9,
        "B10": b10,
        "B14": b11,                # остаточная стоимость → оборудование (v0)
        "B26": debt,               # долгосрочные займы
        "B27": paid_in,            # обыкновенные акции
        "B32": retained,           # нераспределённая прибыль
    }
    balance = build_balance(balance_leaves, n)

    return income, cashflow, balance, profit_use
