"""Календарный план (этапы подготовительной фазы) → вклад в отчёты (SPEC §9).

- ``asset``  → синтетический ``Asset`` (реюз машинерии активов: capex C14, амортизация I17/B10,
  остаточная B14) — как выкуп лизинга. Актив ставится на баланс в месяц завершения.
- ``expense`` → отток «издержки подготовительного периода» (C15); признание сразу (I21) либо,
  при ``amortize_months>0``, капитализация в расходы будущих периодов (B15) со списанием (I21).
- ``production`` → старт продукта (K3; здесь стоимости не несёт).

K1: расписание разрешает связи-предшественники (финиш→старт, ``start_month`` = лаг) с защитой
от циклов; иерархия — стоимость несут только листья (этапы-группы стоимости не несут).
K2: стоимость этапа = Σ(количество × цена ресурса) при наличии ресурсов, иначе прямая ``cost``;
``payment_delay_months`` ресурса сдвигает оплату (C15) относительно начисления → кредиторка
(B23). У этапов-активов оплата — в момент постановки на баланс (задержка ресурса не применяется).
"""
from __future__ import annotations

from decimal import Decimal

from ..models import Asset
from ..models.calendar import Resource, Stage
from ..models.project import ProjectModel
from ..money import ZERO, D
from ..series import cumulative, zeros


def _stage_cost(stage: Stage, res_by_id: dict[str, Resource]) -> Decimal:
    """Стоимость этапа: Σ(количество × цена ресурса) либо прямая ``cost`` (если нет ресурсов)."""
    if stage.resources:
        total = ZERO
        for sr in stage.resources:
            r = res_by_id.get(sr.resource_id)
            if r is not None:
                total += sr.quantity * r.unit_price
        return total
    return stage.cost


def _resolve_schedule(stages: list[Stage]) -> dict[str, tuple[int, int]]:
    """Эффективные (start, finish) по каждому этапу с учётом предшественников (финиш→старт)."""
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
    cal = model.investment_plan.calendar
    res_by_id = {r.id: r for r in cal.resources}
    groups = _group_ids(cal.stages)
    sched = _resolve_schedule(cal.stages)
    out: list[Asset] = []
    for st in cal.stages:
        if st.kind != "asset" or st.id in groups:
            continue
        cost = _stage_cost(st, res_by_id)
        if cost <= ZERO:
            continue
        _, finish = sched[st.id]
        out.append(Asset(
            name=f"Этап: {st.name}", cost=cost, purchase_month=finish,
            life_months=st.asset_life_months, category=st.asset_category,
        ))
    return out


def _stage_cash(st: Stage, res_by_id: dict[str, Resource], start: int, n: int,
                cash_total: list[Decimal]) -> None:
    """Оплата этапа (C15): по ресурсам со сдвигом на ``payment_delay_months``; прямая — без сдвига."""
    dur = st.duration_months
    if st.resources:
        for sr in st.resources:
            r = res_by_id.get(sr.resource_id)
            if r is None:
                continue
            cost_r = sr.quantity * r.unit_price
            if cost_r == ZERO:
                continue
            per_r = cost_r / D(dur)
            for t in range(max(start, 0), min(start + dur, n)):
                pay = t + r.payment_delay_months
                if 0 <= pay < n:
                    cash_total[pay] += per_r
    else:
        per = st.cost / D(dur)
        for t in range(max(start, 0), min(start + dur, n)):
            cash_total[t] += per


def stage_expenses(
    model: ProjectModel, n: int,
) -> tuple[list[Decimal], list[Decimal], list[Decimal], list[Decimal]]:
    """Обычные этапы → (C15 оплата, I21 признание, B15 расходы будущих периодов, B23 кредиторка)."""
    cal = model.investment_plan.calendar
    res_by_id = {r.id: r for r in cal.resources}
    groups = _group_ids(cal.stages)
    sched = _resolve_schedule(cal.stages)
    i21 = zeros(n)
    accrual = zeros(n)   # начисление стоимости (для разрыва с оплатой → B23)
    cash = zeros(n)      # оплата (C15)
    cap = zeros(n)       # прирост капитализации в РБП (B15)
    amort = zeros(n)     # прирост списания РБП
    for st in cal.stages:
        if st.kind != "expense" or st.id in groups:
            continue
        cost = _stage_cost(st, res_by_id)
        if cost <= ZERO:
            continue
        start, finish = sched[st.id]
        per = cost / D(st.duration_months)
        deferred = st.amortize_months > 0
        for t in range(max(start, 0), min(finish, n)):
            accrual[t] += per
            if deferred:
                cap[t] += per                   # капитализируем в РБП, издержку отложим
            else:
                i21[t] += per                   # признаём издержку сразу
        if deferred:
            amort_per = cost / D(st.amortize_months)
            for t in range(max(finish, 0), min(finish + st.amortize_months, n)):
                i21[t] += amort_per             # списание РБП в издержки
                amort[t] += amort_per
        _stage_cash(st, res_by_id, start, n, cash)
    cap_cum, amort_cum = cumulative(cap), cumulative(amort)
    b15 = [cap_cum[t] - amort_cum[t] for t in range(n)]        # уровень РБП на конец периода
    acc_cum, cash_cum = cumulative(accrual), cumulative(cash)
    b23 = [acc_cum[t] - cash_cum[t] for t in range(n)]         # начислено − оплачено = кредиторка
    return cash, i21, b15, b23
