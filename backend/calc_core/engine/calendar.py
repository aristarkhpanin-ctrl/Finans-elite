"""Календарный план (этапы подготовительной фазы) → вклад в отчёты (SPEC §9).

K0: прямая стоимость, явный ``start_month``, равномерное распределение по длительности.
- ``asset``  → синтетический ``Asset`` (реюз машинерии активов: capex C14, амортизация I17/B10,
  остаточная B14) — как выкуп лизинга. Актив ставится на баланс в месяц завершения.
- ``expense`` → отток «издержки подготовительного периода» (C15); признание сразу (I21) либо,
  при ``amortize_months>0``, капитализация в расходы будущих периодов (B15) со списанием (I21).
- ``production`` → старт продукта (K3; здесь стоимости не несёт).

Разрешение связей/иерархии/ресурсов — в следующих фазах (K1–K2); хелперы ``_stage_cost`` /
``_stage_start`` пока тривиальны.
"""
from __future__ import annotations

from decimal import Decimal

from ..models import Asset
from ..models.calendar import Stage
from ..models.project import ProjectModel
from ..money import ZERO, D
from ..series import cumulative, zeros


def _stage_cost(stage: Stage) -> Decimal:
    """Стоимость этапа (K2: + Σ ресурсов)."""
    return stage.cost


def _stage_start(stage: Stage) -> int:
    """Эффективный старт этапа (K1: + разрешение предшественников)."""
    return stage.start_month


def stage_assets(model: ProjectModel) -> list[Asset]:
    """Синтетические ОС из этапов-активов — обрабатываются машинерией активов наравне с плановыми."""
    out: list[Asset] = []
    for st in model.investment_plan.calendar.stages:
        if st.kind != "asset":
            continue
        cost = _stage_cost(st)
        if cost <= ZERO:
            continue
        out.append(Asset(
            name=f"Этап: {st.name}", cost=cost,
            purchase_month=_stage_start(st) + st.duration_months,
            life_months=st.asset_life_months, category=st.asset_category,
        ))
    return out


def stage_expenses(model: ProjectModel, n: int) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    """Обычные этапы → (C15 отток, I21 признание издержек, B15 уровень расходов будущих периодов)."""
    c15 = zeros(n)
    i21 = zeros(n)
    cap = zeros(n)     # прирост капитализации в РБП (B15) по месяцам стройки
    amort = zeros(n)   # прирост списания РБП по месяцам
    for st in model.investment_plan.calendar.stages:
        if st.kind != "expense":
            continue
        cost = _stage_cost(st)
        if cost <= ZERO:
            continue
        start = _stage_start(st)
        finish = start + st.duration_months
        per = cost / D(st.duration_months)
        deferred = st.amortize_months > 0
        for t in range(max(start, 0), min(finish, n)):
            c15[t] += per                       # отток подготовительного периода
            if deferred:
                cap[t] += per                   # капитализируем в РБП, издержку отложим
            else:
                i21[t] += per                   # признаём издержку сразу
        if deferred:
            amort_per = cost / D(st.amortize_months)
            for t in range(max(finish, 0), min(finish + st.amortize_months, n)):
                i21[t] += amort_per             # списание РБП в издержки
                amort[t] += amort_per
    cap_cum = cumulative(cap)
    amort_cum = cumulative(amort)
    b15 = [cap_cum[t] - amort_cum[t] for t in range(n)]   # уровень РБП на конец периода
    return c15, i21, b15
