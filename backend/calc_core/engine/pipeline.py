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
from ..money import D, ONE, ZERO
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


def _inflation_index(annual_rate, n: int) -> list[Decimal]:
    """Накопленный индекс инфляции по месяцам (SPEC §3).

    Период 0 — база (индекс 1); далее умножается на месячную ставку
    ``(1+годовая)^(1/12)``. Нулевая ставка → ряд из единиц (без индексации).
    """
    r = D(annual_rate)
    if r == ZERO:
        return [ONE for _ in range(n)]
    m = (ONE + r) ** (ONE / D(12)) - ONE
    out = zeros(n)
    idx = ONE
    for t in range(n):
        out[t] = idx
        idx = idx * (ONE + m)
    return out


def _sales(model: ProjectModel, n: int, vat_rate: Decimal,
           fx: list[Decimal], fx_prev: list[Decimal], idx_sales: list[Decimal]):
    """Сбыт → (I1 нетто, C1 деньги с НДС, B2 дебиторка, B24 авансы, исходящий НДС, I25).

    ОПУ — без НДС (I1 = нетто-выручка); деньги и оборотный капитал — с НДС. Экспортные
    (валютные) строки — без НДС, с пересчётом по ``fx[t]``; их дебиторка/авансы
    переоцениваются → курсовая разница ``i25_sales`` (SPEC §22.3).
    """
    i1 = zeros(n)
    c1 = zeros(n)
    b2 = zeros(n)
    b24 = zeros(n)
    vat_out = zeros(n)        # исходящий НДС начислено (по отгрузке)
    vat_out_paid = zeros(n)   # исходящий НДС в полученных деньгах (по оплате)
    recv_f = zeros(n)         # валютная дебиторка (в валюте) — для переоценки
    adv_f = zeros(n)          # валютные авансы (в валюте) — для переоценки
    one_plus = Decimal(1) + vat_rate
    for line in model.operating_plan.sales:
        vol = _pad(line.volume, n)
        price = _pad(line.price, n)
        if line.foreign:
            revenue = [vol[t] * price[t] for t in range(n)]      # валюта: без рублёвой инфляции
        else:
            revenue = [vol[t] * price[t] * idx_sales[t] for t in range(n)]  # индексация цен
        if line.foreign:
            # Экспорт: без НДС; выручка/деньги/дебиторка в валюте → пересчёт по FX.
            cash, recv, adv = sales_timing(revenue, line.payment, n)
            i1 = add(i1, [revenue[t] * fx[t] for t in range(n)])      # начислено по курсу отгрузки
            c1 = add(c1, [cash[t] * fx[t] for t in range(n)])        # деньги по курсу получения
            b2 = add(b2, [recv[t] * fx[t] for t in range(n)])
            b24 = add(b24, [adv[t] * fx[t] for t in range(n)])
            recv_f = add(recv_f, recv)
            adv_f = add(adv_f, adv)
        else:
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
    # Курсовая разница по валютным дебиторке/авансам (на остаток начала периода).
    i25_sales = zeros(n)
    for t in range(n):
        net_start = (recv_f[t - 1] - adv_f[t - 1]) if t > 0 else ZERO
        i25_sales[t] = net_start * (fx[t] - fx_prev[t])
    return i1, c1, b2, b24, vat_out, vat_out_paid, i25_sales


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


def _materials_and_wages(model: ProjectModel, n: int, vat_rate: Decimal,
                         idx_direct: list[Decimal], idx_wages: list[Decimal]):
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
        base = _pad(line.amount, n)
        idx = idx_direct if line.kind == DirectCostKind.MATERIALS else idx_wages
        amt = [base[t] * idx[t] for t in range(n)]               # индексация инфляцией
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


def _fixed(model: ProjectModel, n: int, vat_rate: Decimal,
           fx: list[Decimal], fx_prev: list[Decimal],
           idx_wages: list[Decimal], idx_general: list[Decimal]):
    """Постоянные издержки → (группы начисления I10–I15; C5, C6 деньги; кредиторка;
    входной НДС по общим издержкам; издержки за счёт прибыли I24; курсовая разница I25).

    Общие издержки (услуги) облагаются НДС; затраты на персонал — нет. Издержки с флагом
    «из прибыли» (невычитаемые, SPEC §12/§22.1) не попадают в I10–I15 (не уменьшают I23),
    а накапливаются в I24; их выплата проходит как общие издержки (в v0 — без НДС).
    Валютные издержки (`foreign`, услуги без НДС) пересчитываются по ``fx[t]``; их
    кредиторка переоценивается → ``i25_fixed`` (SPEC §22.3).
    """
    groups = {fn: zeros(n) for fn in CostFunction}
    c5 = zeros(n)  # общие издержки (с НДС)
    c6 = zeros(n)  # затраты на персонал (без НДС)
    payables = zeros(n)
    vat_in = zeros(n)        # входной НДС начислено
    vat_in_paid = zeros(n)   # входной НДС в оплаченных издержках (по оплате)
    i24 = zeros(n)  # издержки, отнесённые на прибыль (невычитаемые)
    payable_f = zeros(n)  # валютная кредиторка (в валюте) — для переоценки
    one_plus = Decimal(1) + vat_rate
    contrib = ONE + model.settings.payroll_contribution_rate  # загрузка ФОТ страховыми взносами
    for line in model.operating_plan.fixed_costs:
        amt = _pad(line.amount, n)
        if line.foreign:
            # Валютная издержка (услуга, без НДС): пересчёт по FX; кредиторка переоценивается.
            cash_f, pay_f = cost_timing(amt, line.payment_delay_months, n)
            groups[line.function] = add(groups[line.function], [amt[t] * fx[t] for t in range(n)])
            cash_b = [cash_f[t] * fx[t] for t in range(n)]
            if line.function in _STAFF_FUNCTIONS:
                c6 = add(c6, cash_b)
            else:
                c5 = add(c5, cash_b)
            payables = add(payables, [pay_f[t] * fx[t] for t in range(n)])
            payable_f = add(payable_f, pay_f)
            continue
        # Индексация инфляцией (ЗП — по группе зарплаты, прочее — по общей).
        idx_inf = idx_wages if line.function in _STAFF_FUNCTIONS else idx_general
        amt = [amt[t] * idx_inf[t] for t in range(n)]
        if line.from_profit:
            # За счёт прибыли: начисление → I24 (не в I10–I15); выплата без НДС.
            cash, pay = cost_timing(amt, line.payment_delay_months, n)
            c5 = add(c5, cash)
            payables = add(payables, pay)
            i24 = add(i24, amt)
            continue
        if line.function in _STAFF_FUNCTIONS:
            # Загруженная стоимость персонала = ЗП + страховые взносы (база — ФОТ).
            loaded = [amt[t] * contrib for t in range(n)]
            groups[line.function] = add(groups[line.function], loaded)
            cash, pay = cost_timing(loaded, line.payment_delay_months, n)
            c6 = add(c6, cash)
            payables = add(payables, pay)
        else:
            groups[line.function] = add(groups[line.function], amt)
            gross = [amt[t] * one_plus for t in range(n)]
            cash, pay = cost_timing(gross, line.payment_delay_months, n)
            vat_amt = [amt[t] * vat_rate for t in range(n)]
            vat_cash, _ = cost_timing(vat_amt, line.payment_delay_months, n)
            c5 = add(c5, cash)
            payables = add(payables, pay)
            vat_in = add(vat_in, vat_amt)
            vat_in_paid = add(vat_in_paid, vat_cash)
    # Курсовая разница по валютной кредиторке (на остаток начала периода): рост курса → убыток.
    i25_fixed = zeros(n)
    for t in range(n):
        pay_start = payable_f[t - 1] if t > 0 else ZERO
        i25_fixed[t] = -pay_start * (fx[t] - fx_prev[t])
    return groups, c5, c6, payables, vat_in, i24, vat_in_paid, i25_fixed


def _assets(model: ProjectModel, n: int):
    """Активы → (capex, амортизация, поступления от продажи C16, прочие доходы/издержки
    I20/I21, выбытие первонач. стоимости и накопл. амортизации).

    Продажа (``sale_month``): амортизация прекращается, остаточная стоимость списывается,
    поступления идут в C16, финансовый результат (цена − остаточная) — в I20 (прибыль) или
    I21 (убыток). Балансовый инвариант сохраняется (SPEC §9).
    """
    capex = zeros(n)
    dep = zeros(n)
    proceeds = zeros(n)        # → C16
    other_income = zeros(n)    # → I20 (прибыль от продажи)
    other_expense = zeros(n)   # → I21 (убыток от продажи)
    b9_disposal = zeros(n)     # выбытие первоначальной стоимости
    b10_disposal = zeros(n)    # выбытие накопленной амортизации
    for asset in model.investment_plan.assets:
        p = asset.purchase_month
        if 0 <= p < n:
            capex[p] += asset.cost
        d = asset.monthly_depreciation()
        end = min(p + asset.life_months, n)
        sale_m = asset.sale_month
        if sale_m is not None:
            end = min(end, sale_m)              # амортизация прекращается в месяц продажи
        acc_dep = ZERO
        for t in range(max(p, 0), end):
            dep[t] += d
            acc_dep += d
        if sale_m is not None and 0 <= sale_m < n:
            residual = asset.cost - acc_dep
            proceeds[sale_m] += asset.sale_price
            gain = asset.sale_price - residual
            if gain >= 0:
                other_income[sale_m] += gain
            else:
                other_expense[sale_m] += -gain
            b9_disposal[sale_m] += asset.cost
            b10_disposal[sale_m] += acc_dep
    return capex, dep, proceeds, other_income, other_expense, b9_disposal, b10_disposal


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


def _loans(model: ProjectModel, n: int, fx: list[Decimal], fx_prev: list[Decimal]):
    """Займы (основные и валютные) → потоки в основной валюте + переоценка долга.

    Для валютного займа график (поступление, тело, проценты) считается в валюте займа и
    пересчитывается в основную по ``fx[t]``; остаток долга = ``остаток_валюте · fx[t]``,
    а его курсовая переоценка (на остаток начала периода) идёт в ``I25`` (рост курса →
    убыток). Возвращает кортеж рядов в основной валюте.
    """
    proceeds = zeros(n)
    principal = zeros(n)
    interest_all = zeros(n)       # → C24 (касса)
    interest_cost = zeros(n)      # → I18 (вычитаемые)
    interest_profit = zeros(n)    # → I24 (невычитаемые)
    debt = zeros(n)               # → B26 (вклад займов в долг, в основной валюте)
    reval = zeros(n)              # → I25 (курсовая разница по долгу)
    ones = [ONE] * n
    for loan in model.financing.loans:
        pr_f, pp_f, ii_f = _loan_schedule(loan, n)            # в валюте займа
        rate, rate_prev = (fx, fx_prev) if loan.foreign else (ones, ones)
        bal_f = cumulative([pr_f[t] - pp_f[t] for t in range(n)])  # остаток на конец периода
        pr_b = [pr_f[t] * rate[t] for t in range(n)]
        pp_b = [pp_f[t] * rate[t] for t in range(n)]
        ii_b = [ii_f[t] * rate[t] for t in range(n)]
        debt_b = [bal_f[t] * rate[t] for t in range(n)]
        rev = zeros(n)
        for t in range(n):
            bal_start = bal_f[t - 1] if t > 0 else ZERO       # остаток на начало периода
            rev[t] = -bal_start * (rate[t] - rate_prev[t])    # рост курса долга → убыток
        proceeds = add(proceeds, pr_b)
        principal = add(principal, pp_b)
        interest_all = add(interest_all, ii_b)
        if loan.interest_on_profit:
            interest_profit = add(interest_profit, ii_b)
        else:
            interest_cost = add(interest_cost, ii_b)
        debt = add(debt, debt_b)
        reval = add(reval, rev)
    return proceeds, principal, interest_all, interest_cost, interest_profit, debt, reval


def _equity(model: ProjectModel, n: int) -> list[Decimal]:
    eq = zeros(n)
    for inj in model.financing.equity:
        if 0 <= inj.month < n:
            eq[inj.month] += inj.amount
    return eq


def _fx_series(env, n: int) -> list[Decimal]:
    """Курс второй валюты по периодам (основная валюта за единицу второй).

    Недостающие хвосты ряда продлеваются последним известным курсом; пустой ряд —
    постоянный стартовый курс (одна валюта, переоценки нет).
    """
    if not env.fx_rate:
        return [D(env.fx_open) for _ in range(n)]
    out = zeros(n)
    last = D(env.fx_open)
    for t in range(n):
        if t < len(env.fx_rate):
            last = D(env.fx_rate[t])
        out[t] = last
    return out


def run_pipeline(model: ProjectModel, auto: AutoInjection | None = None):
    """Выполнить расчёт и вернуть (income, cashflow, balance, profit_use, warnings).

    ``auto`` — инъекция автофинансирования (проценты в ОПУ и денежные потоки кредитной
    линии); по умолчанию отсутствует.
    """
    n = model.n
    sb = model.company.starting_balance
    auto = auto or AutoInjection.zero(n)

    # Валютный контур: курс второй валюты по периодам и опорная валютная позиция (SPEC §3).
    env = model.environment
    fx = _fx_series(env, n)
    fx_prev = [D(env.fx_open)] + fx[:-1]          # курс предыдущего периода (t=0 — стартовый)
    fm = sb.foreign_monetary                       # монетарный актив во 2-й валюте (ед. валюты)
    opening_foreign = fm * D(env.fx_open)          # его стоимость в основной валюте на старте

    # Проверка сходимости стартового баланса (SPEC §16), включая валютную позицию.
    if abs(sb.assets() + opening_foreign - sb.liabilities_equity()) > Decimal("0.01"):
        raise ModelError(
            f"Стартовый баланс не сходится: актив {sb.assets() + opening_foreign} != пассив "
            f"{sb.liabilities_equity()}"
        )

    settings = model.settings
    vat_rate = settings.vat_rate

    # Переоценка валютной позиции → курсовая разница (I25) и валютный актив (B6) (SPEC §22.3).
    b6_foreign = [fm * fx[t] for t in range(n)]
    i25_fx = [fm * (fx[t] - fx_prev[t]) for t in range(n)]

    # --- индексы инфляции по группам (SPEC §3) ---
    idx_sales = _inflation_index(settings.inflation_sales, n)
    idx_direct = _inflation_index(settings.inflation_direct, n)
    idx_wages = _inflation_index(settings.inflation_wages, n)
    idx_general = _inflation_index(settings.inflation_general, n)

    # --- операционный контур (accrual + cash + оборотный капитал + запасы + НДС) ---
    i1, c1, b2, b24, vat_out, vat_out_paid, i25_sales = _sales(
        model, n, vat_rate, fx, fx_prev, idx_sales)
    tp, tq = _volumes(model, n)
    mc, wc, c2, c3, b3, pay_direct, vat_in_mat, vat_in_paid_mat = _materials_and_wages(
        model, n, vat_rate, idx_direct, idx_wages)
    # Готовая продукция: себестоимость (I5, I6) признаётся при продаже (SPEC §6, §22.8)
    i5, i6, b5, inv_warnings = finished_goods(tp, tq, mc, wc, n, settings.inventory_method)
    fixed, c5, c6, pay_fixed, vat_in_fixed, i24_fixed, vat_in_paid_fixed, i25_fixed = _fixed(
        model, n, vat_rate, fx, fx_prev, idx_wages, idx_general)
    b23 = add(pay_direct, pay_fixed)

    # --- инвестиции и амортизация (capex в баланс — по нетто; деньги — с НДС) ---
    capex, dep, asset_proceeds, asset_income, asset_expense, b9_disp, b10_disp = _assets(model, n)
    capex_gross = [capex[t] * (Decimal(1) + vat_rate) for t in range(n)]
    vat_in_capex = [capex[t] * vat_rate for t in range(n)]
    b9 = [sb.fixed_assets_net + cumulative(capex)[t] - cumulative(b9_disp)[t] for t in range(n)]
    b10 = [cumulative(dep)[t] - cumulative(b10_disp)[t] for t in range(n)]
    b11 = [b9[t] - b10[t] for t in range(n)]

    # Налог на имущество (база — остаточная стоимость, годовая ставка → помесячно)
    prop_monthly = settings.property_tax_rate / Decimal(12)
    i9 = [prop_monthly * b11[t] for t in range(n)]

    # --- займы (основные и валютные; валютные переоцениваются → I25) ---
    (loan_proceeds, loan_principal, loan_interest, loan_interest_cost,
     loan_interest_profit, loan_debt, loan_reval) = _loans(model, n, fx, fx_prev)

    # --- лизинг (операционный): платёж = издержка (I21) + отток (C25) ---
    lease_payments = zeros(n)
    for lease in model.financing.leases:
        for t in range(lease.start_month, min(lease.start_month + lease.term_months, n)):
            if t >= 0:
                lease_payments[t] += lease.monthly_payment

    # --- депозиты/ЦБ: вложение C8, доход C9 (= I20), тело в B6 ---
    c8 = zeros(n)            # вложения в ЦБ (размещение +, возврат −)
    c9 = zeros(n)            # доходы по ЦБ
    deposit_bal = zeros(n)   # тело размещения на конец периода → B6
    for deposit in model.financing.deposits:
        rm = (ONE + deposit.annual_rate) ** (ONE / D(12)) - ONE
        s = deposit.start_month
        e = s + deposit.term_months
        if 0 <= s < n:
            c8[s] += deposit.amount          # размещение (отток)
        if 0 <= e < n:
            c8[e] -= deposit.amount          # возврат тела (приток)
        for t in range(max(s, 0), min(e, n)):
            deposit_bal[t] += deposit.amount
            c9[t] += deposit.amount * rm     # доход за период держания

    equity_in = _equity(model, n)
    dividends = _pad(model.financing.dividends, n)

    # --- Отчёт о прибылях и убытках (начисление) ---
    i3 = [i1[t] * settings.sales_tax_rate for t in range(n)]  # налог с продаж (база — I1)
    income_leaves = {
        "I1": i1,
        "I3": i3,
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
        "I20": add(asset_income, c9),               # прочие доходы + доход по ЦБ
        "I21": add(asset_expense, lease_payments),  # прочие издержки + лизинговые платежи
        "I18": add(loan_interest_cost, auto.pl_interest),
        "I24": add(i24_fixed, loan_interest_profit),
        "I25": add(i25_fx, loan_reval, i25_sales, i25_fixed),
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
    # Налоги: прибыль + имущество + налог с продаж + НДС к уплате (v0: в периоде начисления)
    taxes_cash = add(income["I27"], i9, i3, vat_to_budget)
    cashflow_leaves = {
        "C1": c1,
        "C2": c2,
        "C3": c3,
        "C5": c5,
        "C6": c6,
        "C8": c8,
        "C9": c9,
        "C12": taxes_cash,
        "C14": capex_gross,
        "C16": asset_proceeds,
        "C21": equity_in,
        "C22": add(loan_proceeds, auto.cash_draws),
        "C23": add(loan_principal, auto.cash_principal),
        "C24": add(loan_interest, auto.cash_interest),
        "C25": lease_payments,
        "C26": dividends,
        "C28": c28,
    }
    cashflow = build_cashflow(cashflow_leaves, n)

    # --- Баланс ---
    paid_in = [sb.paid_in_capital + e for e in cumulative(equity_in)]
    debt = [sb.debt + loan_debt[t] for t in range(n)]  # вклад займов в долг (валютные — по FX)
    # Остаток кредитной линии автофинансирования → краткосрочные займы (B22)
    auto_draws_cum = cumulative(auto.cash_draws)
    auto_prin_cum = cumulative(auto.cash_principal)
    auto_debt = [auto_draws_cum[t] - auto_prin_cum[t] for t in range(n)]
    balance_leaves = {
        "B1": cashflow["C29"],     # денежные средства = сальдо Кэш-фло
        "B2": b2,                  # счета к получению (дебиторка, с НДС)
        "B3": b3,                  # сырьё, материалы и комплектующие
        "B5": b5,                  # запасы готовой продукции
        "B6": add(b6_foreign, deposit_bal),  # валютная позиция + депозиты/ЦБ
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
