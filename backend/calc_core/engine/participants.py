"""Доходы участников финансирования (SPEC §17, пакет №7 gap-анализа).

Потоки и индивидуальные NPV/IRR акционеров и кредиторов — новый раздел результата,
строки отчётов не меняются. Акционеры: −C21 + C26 (+ вариант с терминальной
стоимостью — собственный капитал B33 на конец горизонта). Кредиторы: по каждому
займу из того же графика, что строит конвейер; валютные займы — в рублях по FX[t]
(доходность кредитора включает курсовой эффект). Пустое финансирование инертно.
"""
from __future__ import annotations

from ..metrics import annual_to_monthly, irr_annual, npv
from ..models import ProjectModel
from ..money import ONE, ZERO
from ..reports.result import ParticipantFlow
from ..reports.statements import Statement
from .pipeline import _fx_series, _loan_schedule


def compute_participants(model: ProjectModel, cashflow: Statement,
                         balance: Statement, n: int) -> list[ParticipantFlow]:
    """Потоки участников по готовым отчётам и модели; без финансирования — пусто."""
    r_m = annual_to_monthly(model.settings.discount_rate_annual)
    items: list[ParticipantFlow] = []

    # --- Акционеры (совокупно): вложения C21, изъятия C26 ---
    c21, c26 = cashflow["C21"], cashflow["C26"]
    equity_flow = [c26[t] - c21[t] for t in range(n)]
    if any(v != ZERO for v in equity_flow):
        tv = balance["B33"][n - 1]
        flow_tv = list(equity_flow)
        flow_tv[n - 1] += tv
        items.append(ParticipantFlow(
            id="equity", name="Акционеры", kind="equity",
            flow=equity_flow,
            invested=sum(c21, ZERO),
            withdrawn=sum(c26, ZERO),
            npv=npv(equity_flow, r_m),
            irr_annual=irr_annual(equity_flow),
            terminal_value=tv,
            npv_with_terminal=npv(flow_tv, r_m),
            irr_with_terminal_annual=irr_annual(flow_tv),
        ))

    # --- Кредиторы: каждый заём отдельным участником ---
    fx = _fx_series(model.environment, n)
    ones = [ONE] * n
    for i, loan in enumerate(model.financing.loans):
        proceeds, principal, interest = _loan_schedule(loan, n)
        rate = fx if loan.foreign else ones
        flow = [(principal[t] + interest[t] - proceeds[t]) * rate[t] for t in range(n)]
        invested = sum((proceeds[t] * rate[t] for t in range(n)), ZERO)
        if invested == ZERO:
            continue                       # заём вне горизонта — не участник
        # Терминальная стоимость требования: непогашенное тело на конец горизонта
        # (график может выходить за горизонт) — по курсу последнего месяца.
        outstanding = sum((proceeds[t] - principal[t] for t in range(n)), ZERO)
        tv = outstanding * rate[n - 1]
        flow_tv = list(flow)
        flow_tv[n - 1] += tv
        items.append(ParticipantFlow(
            id=f"loan:{i}", name=loan.name, kind="lender",
            flow=flow,
            invested=invested,
            withdrawn=sum(((principal[t] + interest[t]) * rate[t] for t in range(n)), ZERO),
            npv=npv(flow, r_m),
            irr_annual=irr_annual(flow),
            terminal_value=tv,
            npv_with_terminal=npv(flow_tv, r_m),
            irr_with_terminal_annual=irr_annual(flow_tv),
        ))
    return items


__all__ = ["compute_participants"]
