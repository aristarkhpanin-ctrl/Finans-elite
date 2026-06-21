"""Публичная точка входа расчётного ядра: ``run(model) -> CalcResult``.

Чистая детерминированная функция (SPEC §1). После расчёта проверяются балансовые
инварианты (SPEC §16); их нарушение — баг ядра (``InvariantError``).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..metrics import (
    annual_to_monthly,
    discounted_payback_months,
    irr_annual,
    npv,
    payback_months,
    profitability_index,
)
from ..models import ProjectModel
from ..money import almost_equal
from ..reports.ratios import compute_ratios
from ..reports.result import CalcResult, InvestmentMetrics
from ..series import add
from ..version import ENGINE_VERSION
from .errors import InvariantError
from .pipeline import run_pipeline


@dataclass
class CalcOptions:
    """Параметры расчёта."""

    check_invariants: bool = True


def run(model: ProjectModel, options: CalcOptions | None = None) -> CalcResult:
    """Рассчитать проект и вернуть отчёты, показатели и метаданные."""
    options = options or CalcOptions()
    n = model.n

    income, cashflow, balance, profit_use, warnings = run_pipeline(model)

    if options.check_invariants:
        _check_invariants(income, cashflow, balance, profit_use, n)

    metrics = _metrics(model, cashflow)
    ratios = compute_ratios(
        income, cashflow, balance, profit_use,
        model.financing.common_shares, n,
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
        warnings=warnings,
    )


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
    # v0: поток до финансирования = операционная + инвестиционная деятельность (SPEC §17/§22).
    net_flow = add(cashflow["C13"], cashflow["C20"])
    r_m = annual_to_monthly(model.settings.discount_rate_annual)
    return InvestmentMetrics(
        npv=npv(net_flow, r_m),
        irr_annual=irr_annual(net_flow),
        pi=profitability_index(net_flow, r_m),
        pb_months=payback_months(net_flow),
        dpb_months=discounted_payback_months(net_flow, r_m),
    )
