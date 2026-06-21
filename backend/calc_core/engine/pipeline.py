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

from ..models import CostFunction, DirectCostKind, ProjectModel, RepaymentType, VatBasis
from ..money import D, ZERO
from ..series import add, cumulative, zeros
from ..reports.statements import (
    build_balance,
    build_cashflow,
    build_income,
    build_profit_use,
)
from .errors import ModelError
from .financing_auto import AutoInjection
from .inventory import finished_goods, purchase_schedule
from .timing import cost_timing, sales_timing
from .vat import settle_vat

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


def _sales(model: ProjectModel, n: int, vat_rate: Decimal):
    """Сбыт → (I1 нетто, C1 деньги с НДС, B2 дебиторка, B24 авансы, исходящий НДС).

    ОПУ — без НДС (I1 = нетто-выручка); деньги и оборотный капитал — с НДС.
    """
    i1 = zeros(n)
    c1 = zeros(n)
    b2 = zeros(n)
    b24 = zeros(n)
    vat_out = zeros(n)        # исходящий НДС начислено (по отгрузке)
    vat_out_paid = zeros(n)   # исходящий НДС в полученных деньгах (по оплате)
    one_plus = Decimal(1) + vat_rate
    for line in model.operating_plan.sales:
        vol = _pad(line.volume, n)
        price = _pad(line.price, n)
        revenue = [vol[t] * price[t] for t in range(n)]          # нетто (→ I1)
        gross = [revenue[t] * one_plus for t in range(n)]        # с НДС (→ деньги/WC)
        cash, recv, adv = sales_timing(gross, line.payment, n)
        vat_amt = [revenue[t] * vat_rate for t in range(n)]
        vat_cash, _, _ = sales_timing(vat_amt, line.payment, n)  # НДС в деньгах (та же схема)
        i1 = add(i1, revenue)
        c1 = add(c1, cash)
        b2 = add(b2, recv)
        b24 = add(b24, adv)
        vat_out = add(vat_out, vat_amt)
        vat_out_paid = add(vat_out_paid, vat_cash)
    return i1, c1, b2, b24, vat_out, vat_out_paid


def _volumes(model: ProjectModel, n: int):
    """Агрегированные объёмы → (производство TP, сбыт TQ).

    Производство по продукту = его план производства, либо (по умолчанию) объём сбыта.
    """
    sales_by_prod: dict[str, list[Decimal]] = {}
    for s in model.operating_plan.sales:
        cur = sales_by_prod.get(s.product_id, zeros(n))
        sales_by_prod[s.product_id] = add(cur, _pad(s.volume, n))

    prod_by_prod = dict(sales_by_prod)  # по умолчанию — производство под продажи
    for pl in model.operating_plan.production:
        prod_by_prod[pl.product_id] = _pad(pl.volume, n)

    tq = zeros(n)
    for v in sales_by_prod.values():
        tq = add(tq, v)
    tp = zeros(n)
    for v in prod_by_prod.values():
        tp = add(tp, v)
    return tp, tq


def _materials_and_wages(model: ProjectModel, n: int, vat_rate: Decimal):
    """Прямые издержки → (потребление MC, сдельная ЗП WC; деньги C2, C3 с НДС; сырьё B3;
    кредиторка с НДС; входной НДС по материалам).

    Себестоимость (нетто) попадёт в ОПУ при продаже через пул готовой продукции.
    НДС на материалы — входной (к вычету); сдельная зарплата НДС не облагается.
    """
    mc = zeros(n)  # нетто-стоимость материалов, потреблённых в производстве
    wc = zeros(n)  # сдельная зарплата в производстве
    c2 = zeros(n)
    c3 = zeros(n)
    b3 = zeros(n)
    payables = zeros(n)
    vat_in = zeros(n)        # входной НДС начислено (при закупке)
    vat_in_paid = zeros(n)   # входной НДС в оплаченных закупках (по оплате)
    one_plus = Decimal(1) + vat_rate
    for line in model.operating_plan.direct_costs:
        amt = _pad(line.amount, n)
        if line.kind == DirectCostKind.MATERIALS:
            purchases, raw_inv = purchase_schedule(amt, line.stock_lead_months, n)
            gross = [purchases[t] * one_plus for t in range(n)]
            cash, pay = cost_timing(gross, line.payment_delay_months, n)
            vat_amt = [purchases[t] * vat_rate for t in range(n)]
            vat_cash, _ = cost_timing(vat_amt, line.payment_delay_months, n)
            mc = add(mc, amt)
            c2 = add(c2, cash)
            b3 = add(b3, raw_inv)            # запас сырья — по нетто-стоимости
            payables = add(payables, pay)
            vat_in = add(vat_in, vat_amt)
            vat_in_paid = add(vat_in_paid, vat_cash)
        else:  # сдельная зарплата — без НДС
            cash, pay = cost_timing(amt, line.payment_delay_months, n)
            wc = add(wc, amt)
            c3 = add(c3, cash)
            payables = add(payables, pay)
    return mc, wc, c2, c3, b3, payables, vat_in, vat_in_paid


def _fixed(model: ProjectModel, n: int, vat_rate: Decimal):
    """Постоянные издержки → (группы начисления I10–I15; C5, C6 деньги; кредиторка;
    входной НДС по общим издержкам; издержки за счёт прибыли I24).

    Общие издержки (услуги) облагаются НДС; затраты на персонал — нет. Издержки с флагом
    «из прибыли» (невычитаемые, SPEC §12/§22.1) не попадают в I10–I15 (не уменьшают I23),
    а накапливаются в I24; их выплата проходит как общие издержки (в v0 — без НДС).
    """
    groups = {fn: zeros(n) for fn in CostFunction}
    c5 = zeros(n)  # общие издержки (с НДС)
    c6 = zeros(n)  # затраты на персонал (без НДС)
    payables = zeros(n)
    vat_in = zeros(n)        # входной НДС начислено
    vat_in_paid = zeros(n)   # входной НДС в оплаченных издержках (по оплате)
    i24 = zeros(n)  # издержки, отнесённые на прибыль (невычитаемые)
    one_plus = Decimal(1) + vat_rate
    for line in model.operating_plan.fixed_costs:
        amt = _pad(line.amount, n)
        if line.from_profit:
            # За счёт прибыли: начисление → I24 (не в I10–I15); выплата без НДС.
            cash, pay = cost_timing(amt, line.payment_delay_months, n)
            c5 = add(c5, cash)
            payables = add(payables, pay)
            i24 = add(i24, amt)
            continue
        groups[line.function] = add(groups[line.function], amt)
        if line.function in _STAFF_FUNCTIONS:
            cash, pay = cost_timing(amt, line.payment_delay_months, n)
            c6 = add(c6, cash)
            payables = add(payables, pay)
        else:
            gross = [amt[t] * one_plus for t in range(n)]
            cash, pay = cost_timing(gross, line.payment_delay_months, n)
            vat_amt = [amt[t] * vat_rate for t in range(n)]
            vat_cash, _ = cost_timing(vat_amt, line.payment_delay_months, n)
            c5 = add(c5, cash)
            payables = add(payables, pay)
            vat_in = add(vat_in, vat_amt)
            vat_in_paid = add(vat_in_paid, vat_cash)
    return groups, c5, c6, payables, vat_in, i24, vat_in_paid


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


def run_pipeline(model: ProjectModel, auto: AutoInjection | None = None):
    """Выполнить расчёт и вернуть (income, cashflow, balance, profit_use, warnings).

    ``auto`` — инъекция автофинансирования (проценты в ОПУ и денежные потоки кредитной
    линии); по умолчанию отсутствует.
    """
    n = model.n
    sb = model.company.starting_balance
    auto = auto or AutoInjection.zero(n)

    # Проверка сходимости стартового баланса (SPEC §16).
    if abs(sb.assets() - sb.liabilities_equity()) > Decimal("0.01"):
        raise ModelError(
            f"Стартовый баланс не сходится: актив {sb.assets()} != пассив "
            f"{sb.liabilities_equity()}"
        )

    settings = model.settings
    vat_rate = settings.vat_rate

    # --- операционный контур (accrual + cash + оборотный капитал + запасы + НДС) ---
    i1, c1, b2, b24, vat_out, vat_out_paid = _sales(model, n, vat_rate)
    tp, tq = _volumes(model, n)
    mc, wc, c2, c3, b3, pay_direct, vat_in_mat, vat_in_paid_mat = _materials_and_wages(
        model, n, vat_rate)
    # Готовая продукция: себестоимость (I5, I6) признаётся при продаже (SPEC §6)
    i5, i6, b5, inv_warnings = finished_goods(tp, tq, mc, wc, n)
    fixed, c5, c6, pay_fixed, vat_in_fixed, i24_fixed, vat_in_paid_fixed = _fixed(
        model, n, vat_rate)
    b23 = add(pay_direct, pay_fixed)

    # --- инвестиции и амортизация (capex в баланс — по нетто; деньги — с НДС) ---
    capex, dep = _assets(model, n)
    capex_gross = [capex[t] * (Decimal(1) + vat_rate) for t in range(n)]
    vat_in_capex = [capex[t] * vat_rate for t in range(n)]
    b9 = [sb.fixed_assets_net + c for c in cumulative(capex)]
    b10 = list(cumulative(dep))
    b11 = [b9[t] - b10[t] for t in range(n)]

    # Налог на имущество (база — остаточная стоимость, годовая ставка → помесячно)
    prop_monthly = settings.property_tax_rate / Decimal(12)
    i9 = [prop_monthly * b11[t] for t in range(n)]

    # --- займы ---
    loan_proceeds = zeros(n)
    loan_principal = zeros(n)
    loan_interest = zeros(n)          # все проценты (денежная выплата, C24)
    loan_interest_cost = zeros(n)     # проценты на себестоимость → I18 (вычитаемые)
    loan_interest_profit = zeros(n)   # проценты за счёт прибыли → I24 (невычитаемые)
    for loan in model.financing.loans:
        pr, pp, ii = _loan_schedule(loan, n)
        loan_proceeds = add(loan_proceeds, pr)
        loan_principal = add(loan_principal, pp)
        loan_interest = add(loan_interest, ii)
        if loan.interest_on_profit:
            loan_interest_profit = add(loan_interest_profit, ii)
        else:
            loan_interest_cost = add(loan_interest_cost, ii)

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
        "I18": add(loan_interest_cost, auto.pl_interest),
        "I24": add(i24_fixed, loan_interest_profit),
    }
    income = build_income(
        income_leaves, n, settings.profit_tax_rate, settings.profit_tax_benefit_share)

    # --- Использование прибыли (нераспределённая прибыль = B32) ---
    profit_use = build_profit_use(
        net_profit=income["I28"],
        dividends=dividends,
        reserves=zeros(n),
        opening_retained=sb.retained_earnings,
        n=n,
    )
    retained = profit_use["P7"]

    # --- Зачёт НДС (исходящий − входной − кредит → к уплате; избыток → B7) ---
    # Капвложения оплачиваются в периоде приобретения (без отсрочки) → вход. НДС «по
    # оплате» совпадает с начисленным.
    vat_in_accrued = add(vat_in_mat, vat_in_fixed, vat_in_capex)
    vat_in_paid = add(vat_in_paid_mat, vat_in_paid_fixed, vat_in_capex)

    # Момент признания НДС (SPEC §22.2): «по отгрузке» — начисление; «по оплате» — деньги.
    if settings.vat_basis == VatBasis.PAYMENT:
        out_settle, in_settle = vat_out_paid, vat_in_paid
    else:
        out_settle, in_settle = vat_out, vat_in_accrued
    vat_to_budget, credit_carry = settle_vat(out_settle, in_settle, n)

    # Балансовые статьи НДС (разрывы начисление↔признание паркуются, инвариант сохраняется):
    # B7 — входной НДС-актив (накоплен, ещё не зачтён); B21 — отложенный исходящий НДС.
    cum_out_acc, cum_out_set = cumulative(vat_out), cumulative(out_settle)
    cum_in_acc, cum_in_set = cumulative(vat_in_accrued), cumulative(in_settle)
    b7 = zeros(n)
    b21 = zeros(n)
    for t in range(n):
        deferred_out = cum_out_acc[t] - cum_out_set[t]   # начислен, но не признан к уплате
        in_not_settled = cum_in_acc[t] - cum_in_set[t]   # начислен, но не предъявлен к вычету
        b21[t] = max(ZERO, deferred_out)
        # B7 = неиспользованный НДС-кредит + входной НДС вне зачёта + НДС с авансов выданных
        b7[t] = credit_carry[t] + in_not_settled + max(ZERO, -deferred_out)

    # --- Кэш-фло (оплата, с НДС) ---
    c28 = zeros(n)
    if n > 0:
        c28[0] = sb.cash
    # Налоги: прибыль + имущество + НДС к уплате (v0: прямые налоги — в периоде начисления)
    taxes_cash = add(income["I27"], i9, vat_to_budget)
    cashflow_leaves = {
        "C1": c1,
        "C2": c2,
        "C3": c3,
        "C5": c5,
        "C6": c6,
        "C12": taxes_cash,
        "C14": capex_gross,
        "C21": equity_in,
        "C22": add(loan_proceeds, auto.cash_draws),
        "C23": add(loan_principal, auto.cash_principal),
        "C24": add(loan_interest, auto.cash_interest),
        "C26": dividends,
        "C28": c28,
    }
    cashflow = build_cashflow(cashflow_leaves, n)

    # --- Баланс ---
    paid_in = [sb.paid_in_capital + e for e in cumulative(equity_in)]
    debt = [sb.debt + cumulative(loan_proceeds)[t] - cumulative(loan_principal)[t] for t in range(n)]
    # Остаток кредитной линии автофинансирования → краткосрочные займы (B22)
    auto_draws_cum = cumulative(auto.cash_draws)
    auto_prin_cum = cumulative(auto.cash_principal)
    auto_debt = [auto_draws_cum[t] - auto_prin_cum[t] for t in range(n)]
    balance_leaves = {
        "B1": cashflow["C29"],     # денежные средства = сальдо Кэш-фло
        "B2": b2,                  # счета к получению (дебиторка, с НДС)
        "B3": b3,                  # сырьё, материалы и комплектующие
        "B5": b5,                  # запасы готовой продукции
        "B7": b7,                  # краткосрочные предоплаченные расходы (НДС-кредит)
        "B21": b21,                # отсроченные налоговые платежи (отложенный исходящий НДС)
        "B9": b9,
        "B10": b10,
        "B14": b11,                # остаточная стоимость → оборудование (v0)
        "B22": auto_debt,          # краткосрочные займы (кредитная линия)
        "B23": b23,                # счета к оплате (кредиторка)
        "B24": b24,                # полученные авансы
        "B26": debt,               # долгосрочные займы
        "B27": paid_in,            # обыкновенные акции
        "B32": retained,           # нераспределённая прибыль
    }
    balance = build_balance(balance_leaves, n)

    return income, cashflow, balance, profit_use, inv_warnings
