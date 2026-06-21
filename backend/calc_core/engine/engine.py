"""Публичная точка входа расчётного ядра: ``run(model) -> CalcResult``.

Чистая детерминированная функция (SPEC §1). После расчёта проверяются балансовые
инварианты (SPEC §16); их нарушение — баг ядра (``InvariantError``).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..metrics import annual_to_monthly
from ..models import ProjectModel
from ..money import almost_equal
from ..reports.actualization import actualize_cashflow
from ..reports.breakeven import compute_break_even
from ..reports.ratios import compute_ratios
from ..reports.result import CalcResult, InvestmentMetrics, build_investment_metrics
from ..reports.statements import opening_balance
from ..series import add, zeros
from ..version import ENGINE_VERSION
from .errors import InvariantError
from .financing_auto import AutoInjection, solve_credit_line
from .pipeline import run_pipeline

# Параметры сходимости автоподбора финансирования.
_MAX_AUTOFIN_ITER = 100
_AUTOFIN_EPS = Decimal("0.01")


@dataclass
class CalcOptions:
    """Параметры расчёта."""

    check_invariants: bool = True


def run(model: ProjectModel, options: CalcOptions | None = None) -> CalcResult:
    """Рассчитать проект и вернуть отчёты, показатели и метаданные."""
    options = options or CalcOptions()
    n = model.n

    income, cashflow, balance, profit_use, warnings = _solve(model)

    if options.check_invariants:
        _check_invariants(income, cashflow, balance, profit_use, n)

    metrics = _metrics(model, cashflow)
    sb = model.company.starting_balance
    opening = opening_balance(
        sb.cash, sb.fixed_assets_net, sb.debt, sb.paid_in_capital, sb.retained_earnings,
    )
    ratios = compute_ratios(
        income, cashflow, balance, profit_use,
        model.financing.common_shares, n, opening,
    )
    break_even = compute_break_even(income, n)

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
        actualized_cashflow=actualized_cashflow,
        cashflow_variance=cashflow_variance,
        warnings=warnings,
    )


def _solve(model: ProjectModel):
    """Расчёт с автоподбором финансирования (итеративно) либо без него."""
    af = model.financing.auto_financing
    if not af.enabled:
        return run_pipeline(model)

    n = model.n
    opening_cash = model.company.starting_balance.cash
    r = annual_to_monthly(af.annual_rate)

    interest = zeros(n)
    draws = zeros(n)
    principal = zeros(n)
    converged = False
    for _ in range(_MAX_AUTOFIN_ITER):
        # Прогон только с процентами в ОПУ (для налога), без денежных потоков автокредита.
        probe = AutoInjection(interest, zeros(n), zeros(n), zeros(n))
        _, cf, _, _, _ = run_pipeline(model, auto=probe)
        base_flow = [cf["C13"][t] + cf["C20"][t] + cf["C27"][t] for t in range(n)]
        draws, principal, new_interest = solve_credit_line(base_flow, opening_cash, af.min_balance, r)
        if all(abs(new_interest[t] - interest[t]) <= _AUTOFIN_EPS for t in range(n)):
            interest = new_interest
            converged = True
            break
        interest = new_interest

    # Финальный прогон: проценты в ОПУ и денежные потоки кредитной линии.
    final = AutoInjection(interest, draws, principal, interest)
    income, cashflow, balance, profit_use, warnings = run_pipeline(model, auto=final)
    if not converged:
        warnings = warnings + ["Автоподбор финансирования не сошёлся за отведённое число итераций"]
    return income, cashflow, balance, profit_use, warnings


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
