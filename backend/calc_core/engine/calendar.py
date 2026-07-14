"""Календарный план (этапы подготовительной фазы) → вклад в отчёты (SPEC §9).

- ``asset``  → синтетический ``Asset`` (реюз машинерии активов: capex C14, амортизация I17/B10,
  остаточная B14) — как выкуп лизинга. Актив ставится на баланс в месяц завершения.
- ``expense`` → отток «издержки подготовительного периода» (C15); признание сразу (I21) либо,
  при ``amortize_months>0``, капитализация в расходы будущих периодов (B15) со списанием (I21).
- ``production`` → старт продукта (K3; здесь стоимости не несёт).

K1: расписание разрешает связи-предшественники (финиш→старт, ``start_month`` = лаг) с защитой
от циклов; иерархия — стоимость несут только листья (этапы-группы, на которые ссылаются как на
``parent_id``, стоимости не несут). Ресурсы (стоимость = Σ) — K2.
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


def _resolve_schedule(stages: list[Stage]) -> dict[str, tuple[int, int]]:
    """Эффективные (start, finish) по каждому этапу с учётом предшественников (финиш→старт).

    Если задан ``predecessor_id`` — старт = финиш(предшественника) + ``start_month`` (лаг);
    иначе ``start_month`` абсолютный. Циклы/несуществующие ссылки → собственный ``start_month``.
    """
    by_id = {s.id: s for s in stages}
    memo: dict[str, tuple[int, int]] = {}

    def resolve(sid: str, visiting: frozenset[str]) -> tuple[int, int]:
        if sid in memo:
            return memo[sid]
        s = by_id[sid]
        pred = s.predecessor_id
        if pred and pred in by_id and pred not in visiting:
            _, pred_finish = resolve(pred, visiting | {sid})
            start = pred_finish + s.start_month
        else:
            start = s.start_month
        memo[sid] = (start, start + s.duration_months)
        return memo[sid]

    for s in stages:
        resolve(s.id, frozenset())
    return memo


def _group_ids(stages: list[Stage]) -> set[str]:
    """Идентификаторы этапов-групп (на них ссылаются как на родителя) — стоимости не несут."""
    return {s.parent_id for s in stages if s.parent_id is not None}


def stage_assets(model: ProjectModel) -> list[Asset]:
    """Синтетические ОС из этапов-активов — обрабатываются машинерией активов наравне с плановыми."""
    stages = model.investment_plan.calendar.stages
    groups = _group_ids(stages)
    sched = _resolve_schedule(stages)
    out: list[Asset] = []
    for st in stages:
        if st.kind != "asset" or st.id in groups:
            continue
        cost = _stage_cost(st)
        if cost <= ZERO:
            continue
        _, finish = sched[st.id]
        out.append(Asset(
            name=f"Этап: {st.name}", cost=cost, purchase_month=finish,
            life_months=st.asset_life_months, category=st.asset_category,
        ))
    return out


def stage_expenses(model: ProjectModel, n: int) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    """Обычные этапы → (C15 отток, I21 признание издержек, B15 уровень расходов будущих периодов)."""
    stages = model.investment_plan.calendar.stages
    groups = _group_ids(stages)
    sched = _resolve_schedule(stages)
    c15 = zeros(n)
    i21 = zeros(n)
    cap = zeros(n)     # прирост капитализации в РБП (B15) по месяцам стройки
    amort = zeros(n)   # прирост списания РБП по месяцам
    for st in stages:
        if st.kind != "expense" or st.id in groups:
            continue
        cost = _stage_cost(st)
        if cost <= ZERO:
            continue
        start, finish = sched[st.id]
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
