"""Публичная точка входа расчётного ядра: ``run(model) -> CalcResult``.

Чистая детерминированная функция (SPEC §1). После расчёта проверяются балансовые
инварианты (SPEC §16); их нарушение — баг ядра (``InvariantError``).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from ..metrics import annual_to_monthly
from ..models import ProjectModel
from ..money import CALC_CONTEXT, ONE, ZERO, almost_equal
from ..reports.actualization import actualize_cashflow
from ..reports.breakeven import compute_break_even
from ..reports.ratios import compute_ratios
from ..reports.result import CalcResult, InvestmentMetrics, build_investment_metrics
from ..reports.statements import opening_balance
from ..reports.valuation import compute_valuation
from ..series import add, zeros
from ..version import ENGINE_VERSION
from .calendar import compute_budget
from .errors import InvariantError
from .financing_auto import AutoInjection, solve_cash_management
from .margins import compute_product_margins
from .participants import compute_participants
from .pipeline import DetailCollector, _preexisting_net_open, run_pipeline
from .tables import compute_user_tables
from .taxes import TaxInjection, compute_custom_taxes

# Параметры сходимости автоподбора финансирования.
_MAX_AUTOFIN_ITER = 100
_AUTOFIN_EPS = Decimal("0.01")


@dataclass
class CalcOptions:
    """Параметры расчёта."""

    check_invariants: bool = True


def run(model: ProjectModel, options: CalcOptions | None = None) -> CalcResult:
    """Рассчитать проект и вернуть отчёты, показатели и метаданные.

    Все вычисления — в фиксированном контексте ядра (``CALC_CONTEXT``): prec и rounding
    не зависят ни от потока (``getcontext()`` thread-local — воркеры FastAPI иначе считали
    бы с дефолтным prec=28), ни от хоста. Результат детерминирован.
    """
    with localcontext(CALC_CONTEXT):
        return _run(model, options)


def _run(model: ProjectModel, options: CalcOptions | None = None) -> CalcResult:
    options = options or CalcOptions()
    n = model.n

    income, cashflow, balance, profit_use, warnings, details = _solve(model)

    if options.check_invariants:
        _check_invariants(income, cashflow, balance, profit_use, n)

    metrics = _metrics(model, cashflow)
    sb = model.company.starting_balance
    # Остаточная стоимость пред-существующих ОС (purchase_month<0) входит в стартовые ОС (t=−1).
    opening_fixed = sb.fixed_assets_net + _preexisting_net_open(model)
    opening = opening_balance(
        sb.cash, opening_fixed, sb.debt, sb.paid_in_capital, sb.retained_earnings,
        sb.foreign_monetary * model.environment.fx_open,
        receivables=sb.receivables, payables=sb.payables,
        raw_materials=sb.raw_materials, finished_goods=sb.finished_goods,
        short_term_debt=sb.short_term_debt, preferred_capital=sb.preferred_capital,
        reserves=sb.reserves, additional_capital=sb.additional_capital,
        prepaid_expenses=sb.prepaid_expenses, advances_received=sb.advances_received,
    )
    ratios = compute_ratios(
        income, cashflow, balance, profit_use,
        model.financing.common_shares, n, opening,
    )
    break_even = compute_break_even(income, n)
    valuation = compute_valuation(
        income, cashflow, balance,
        model.settings.discount_rate_annual, model.settings.terminal_growth_rate,
        model.settings.valuation_earnings_multiple, model.settings.liquidation_recovery_rate, n,
    )

    actualized_cashflow = None
    cashflow_variance = None
    act = model.actualization
    if act.enabled:
        actualized_cashflow, cashflow_variance = actualize_cashflow(
            cashflow, act.actual_until, act.actuals, n,
        )

    return CalcResult(
        engine_version=ENGINE_VERSION,
        n=n,
        income=income,
        cashflow=cashflow,
        balance=balance,
        profit_use=profit_use,
        metrics=metrics,
        ratios=ratios,
        break_even=break_even,
        valuation=valuation,
        budget=compute_budget(model, n),
        product_margins=compute_product_margins(model, n),
        user_tables=compute_user_tables(model, income, cashflow, balance, profit_use, n),
        details=details,
        participants=compute_participants(model, cashflow, balance, n),
        actualized_cashflow=actualized_cashflow,
        cashflow_variance=cashflow_variance,
        warnings=warnings,
    )


def _solve(model: ProjectModel):
    """Расчёт с автоподбором финансирования (итеративно) либо без него.

    Замкнутый контур «проценты → прибыль → налог → деньги → привлечение → проценты»
    решается методом простой итерации с **адаптивным демпфированием** (SPEC §19/§22.5):
    обычно шаг полный (быстрая сходимость сильной обратной связи через налог), но если
    невязка перестаёт убывать — шаг уменьшается вдвое (защита от колебаний/расходимости).
    Демпфирование не меняет неподвижную точку — только путь к ней.
    """
    af = model.financing.auto_financing
    collector = DetailCollector()   # детализация строк (drill-down) — с финального прогона
    taxes = _custom_taxes(model)    # настраиваемые налоги (SPEC §22.9); None — если их нет
    if not (af.enabled or af.invest_surplus):
        income, cashflow, balance, profit_use, warnings = run_pipeline(
            model, details=collector, taxes=taxes)
        return income, cashflow, balance, profit_use, warnings, collector.build()

    n = model.n
    opening_cash = model.company.starting_balance.cash
    credit_rate = annual_to_monthly(af.annual_rate)
    deposit_rate = annual_to_monthly(af.invest_annual_rate)

    # Замкнутый контур теперь по двум рядам: проценты кредита (I18) и доход депозита (I20).
    # Оба влияют на налог → базовый поток → графики; итерация с адаптивным демпфированием.
    interest = zeros(n)
    income_yield = zeros(n)
    plan = None
    damping = ONE
    prev_residual = None
    converged = False
    for _ in range(_MAX_AUTOFIN_ITER):
        # Пробный прогон: доходы/расходы в ОПУ (для налога), без денежных потоков авто.
        probe = AutoInjection(pl_interest=interest, cash_draws=zeros(n),
                              cash_principal=zeros(n), cash_interest=zeros(n),
                              pl_deposit_income=income_yield)
        _, cf, _, _, _ = run_pipeline(model, auto=probe, taxes=taxes)
        base_flow = [cf["C13"][t] + cf["C20"][t] + cf["C27"][t] for t in range(n)]
        plan = solve_cash_management(base_flow, opening_cash, af.min_balance,
                                     credit_rate, deposit_rate,
                                     credit_on=af.enabled, invest_on=af.invest_surplus)

        residual = max(
            (abs(plan.interest[t] - interest[t]) for t in range(n)), default=ZERO)
        residual = max(residual, max(
            (abs(plan.deposit_income[t] - income_yield[t]) for t in range(n)), default=ZERO))
        if residual <= _AUTOFIN_EPS:
            interest = plan.interest
            income_yield = plan.deposit_income
            converged = True
            break
        # Если невязка не убывает — демпфируем шаг (защита от расходимости).
        if prev_residual is not None and residual >= prev_residual:
            damping = damping / Decimal(2)
        prev_residual = residual
        interest = [interest[t] + damping * (plan.interest[t] - interest[t]) for t in range(n)]
        income_yield = [income_yield[t] + damping * (plan.deposit_income[t] - income_yield[t])
                        for t in range(n)]

    assert plan is not None
    # Финальный прогон: проценты/доход в ОПУ и денежные потоки кредита и депозита.
    final = AutoInjection(
        pl_interest=interest, cash_draws=plan.draws, cash_principal=plan.principal,
        cash_interest=interest, pl_deposit_income=income_yield,
        cash_deposit_income=income_yield, cash_deposit_placement=plan.deposit_placement,
        deposit_balance=plan.deposit_balance)
    income, cashflow, balance, profit_use, warnings = run_pipeline(
        model, auto=final, details=collector, taxes=taxes)
    if not converged:
        warnings = warnings + ["Автоподбор финансирования не сошёлся за отведённое число итераций"]
    return income, cashflow, balance, profit_use, warnings, collector.build()


def _custom_taxes(model: ProjectModel) -> TaxInjection | None:
    """Инъекция настраиваемых налогов (SPEC §22.9); ``None`` при пустом списке.

    Базы — по предварительному прогону без настраиваемых налогов и без автоподбора
    финансирования (решение Q2 в CUSTOM-TAXES-DECOMPOSITION.md): один детерминированный
    проход, циклов «налог ← база ← налог» нет. Пустой список — без предварительного
    прогона (нулевые накладные расходы, модель инертна).
    """
    if not model.environment.taxes:
        return None
    income, cashflow, balance, profit_use, _ = run_pipeline(model)
    return compute_custom_taxes(model, income, cashflow, balance, profit_use, model.n)


def _check_invariants(income, cashflow, balance, profit_use, n: int) -> None:
    for t in range(n):
        # Главный инвариант: актив = пассив (SPEC §16.1).
        if not almost_equal(balance["B20"][t], balance["B34"][t]):
            raise InvariantError(
                f"Баланс не сходится в периоде {t}: "
                f"B20={balance['B20'][t]} != B34={balance['B34'][t]}"
            )
        # Деньги = сальдо Кэш-фло (SPEC §16.2).
        if not almost_equal(balance["B1"][t], cashflow["C29"][t]):
            raise InvariantError(
                f"B1 != C29 в периоде {t}: {balance['B1'][t]} != {cashflow['C29'][t]}"
            )
        # Нераспределённая прибыль = накопленная P7 (SPEC §16.3).
        if not almost_equal(balance["B32"][t], profit_use["P7"][t]):
            raise InvariantError(
                f"B32 != P7 в периоде {t}: {balance['B32'][t]} != {profit_use['P7'][t]}"
            )


def _metrics(model: ProjectModel, cashflow) -> InvestmentMetrics:
    # Поток до финансирования = операционная + инвестиционная деятельность (SPEC §17).
    net_flow = add(cashflow["C13"], cashflow["C20"])
    r_m = annual_to_monthly(model.settings.discount_rate_annual)
    return build_investment_metrics(net_flow, r_m)
