"""Календарный план (этапы подготовительной фазы) → вклад в отчёты и бюджет (SPEC §9).

- ``asset``  → синтетический ``Asset`` (реюз машинерии активов: capex C14, амортизация I17/B10,
  остаточная B14) — как выкуп лизинга. Актив ставится на баланс в месяц завершения.
- ``expense`` → отток «издержки подготовительного периода» (C15); признание сразу (I21) либо,
  при ``amortize_months>0``, капитализация в расходы будущих периодов (B15) со списанием (I21).
- ``production`` → старт продукта (гейт объёма до завершения этапа).

Расписание разрешает связи-предшественники (финиш→старт, ``start_month`` = лаг) с защитой от
циклов; иерархия — стоимость несут только листья. Стоимость = Σ(кол-во×цена ресурса) либо
прямая ``cost``; ``payment_delay_months`` ресурса сдвигает оплату → кредиторка (B23). Тайминг
стоимости: ``uniform`` (равномерно по длительности) либо ``on_finish`` (разово в последний месяц).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from ..models import Asset
from ..models.calendar import Resource, Stage
from ..models.project import ProjectModel
from ..money import ONE, ZERO, D
from ..reports.result import Budget, StageBudget
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


def _schedule(start: int, dur: int, timing: str) -> list[tuple[int, Decimal]]:
    """График начисления стоимости этапа: список (месяц, доля). uniform или on_finish."""
    if timing == "on_finish":
        return [(start + dur - 1, ONE)]              # вся стоимость в последний месяц
    per = ONE / D(dur)
    return [(start + k, per) for k in range(dur)]    # равномерно по длительности


def _payment_graph(stage: Stage, cost: Decimal, graph: list[tuple[int, Decimal]],
                   res_by_id: dict[str, Resource], n: int) -> list[Decimal]:
    """Помесячная **оплата** этапа: график начисления со сдвигом на отсрочку ресурсов.

    Общий помощник для отчётов (C15/B23) и сметы — чтобы «оплата» в бюджетном разрезе
    не могла разойтись с оплатой, которая попадает в кэш-фло. Прямая стоимость (без
    ресурсов) платится без сдвига.
    """
    out = zeros(n)
    if stage.resources:
        for sr in stage.resources:
            r = res_by_id.get(sr.resource_id)
            if r is None:
                continue
            cost_r = sr.quantity * r.unit_price
            for m, frac in graph:
                pay = m + r.payment_delay_months
                if 0 <= pay < n:
                    out[pay] += cost_r * frac
    else:
        for m, frac in graph:
            if 0 <= m < n:
                out[m] += cost * frac
    return out


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


def product_start_months(model: ProjectModel) -> dict[str, int]:
    """Продукт → месяц старта из этапов «производство» (финиш этапа; при нескольких — самый ранний)."""
    cal = model.investment_plan.calendar
    groups = _group_ids(cal.stages)
    sched = _resolve_schedule(cal.stages)
    out: dict[str, int] = {}
    for st in cal.stages:
        if st.kind != "production" or st.id in groups or not st.product_id:
            continue
        _, finish = sched[st.id]
        out[st.product_id] = min(out[st.product_id], finish) if st.product_id in out else finish
    return out


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
        graph = _schedule(start, st.duration_months, st.cost_timing)
        deferred = st.amortize_months > 0
        for m, frac in graph:
            if not 0 <= m < n:
                continue
            amt = cost * frac
            accrual[m] += amt
            if deferred:
                cap[m] += amt                       # капитализируем в РБП, издержку отложим
            else:
                i21[m] += amt                       # признаём издержку сразу
        if deferred:
            amort_per = cost / D(st.amortize_months)
            for t in range(max(finish, 0), min(finish + st.amortize_months, n)):
                i21[t] += amort_per                 # списание РБП в издержки
                amort[t] += amort_per
        # Оплата: по ресурсам со сдвигом на задержку; прямая стоимость — без сдвига.
        for m, amt in enumerate(_payment_graph(st, cost, graph, res_by_id, n)):
            cash[m] += amt
    cap_cum, amort_cum = cumulative(cap), cumulative(amort)
    b15 = [cap_cum[t] - amort_cum[t] for t in range(n)]        # уровень РБП на конец периода
    acc_cum, cash_cum = cumulative(accrual), cumulative(cash)
    b23 = [acc_cum[t] - cash_cum[t] for t in range(n)]         # начислено − оплачено = кредиторка
    return cash, i21, b15, b23


def compute_budget(model: ProjectModel, n: int) -> Budget:
    """Смета по этапам: строки (листья + свёрнутые группы) + помесячный график начисления."""
    cal = model.investment_plan.calendar
    if not cal.stages:
        return Budget(monthly=zeros(n))
    res_by_id = {r.id: r for r in cal.resources}
    groups = _group_ids(cal.stages)
    sched = _resolve_schedule(cal.stages)
    children: dict[str, list[str]] = {}
    for st in cal.stages:
        if st.parent_id is not None:
            children.setdefault(st.parent_id, []).append(st.id)

    monthly = zeros(n)
    monthly_cash = zeros(n)
    leaf: dict[str, tuple[Decimal, int, int]] = {}   # id → (cost, start, finish)
    # Помесячные ряды листьев (для бюджетного Гантта): освоение и оплата.
    leaf_rows: dict[str, tuple[list[Decimal], list[Decimal]]] = {}
    leaf_treatment: dict[str, str] = {}
    # Факт по листьям (план-факт, gap 4.6): id → (actual_cost, actual_start, actual_finish).
    fact_leaf: dict[str, tuple[Optional[Decimal], Optional[int], Optional[int]]] = {}
    for st in cal.stages:
        if st.id in groups:
            continue
        start, finish = sched[st.id]
        accrual, cash = zeros(n), zeros(n)
        if st.kind == "expense":
            cost = _stage_cost(st, res_by_id)
            graph = _schedule(start, st.duration_months, st.cost_timing)
            for m, frac in graph:
                if 0 <= m < n:
                    accrual[m] += cost * frac
            cash = _payment_graph(st, cost, graph, res_by_id, n)
            treatment = "deferred" if st.amortize_months > 0 else "expense"
        elif st.kind == "asset":
            cost = _stage_cost(st, res_by_id)
            if 0 <= finish < n:
                # Актив — разово в месяц постановки (как capex); отсрочки ресурсов машинерия
                # активов не применяет, поэтому оплата совпадает с освоением.
                accrual[finish] += cost
                cash[finish] += cost
            treatment = "asset"
        else:                                     # production — стоимости не несёт
            cost = ZERO
            treatment = "none"
        for m in range(n):
            monthly[m] += accrual[m]
            monthly_cash[m] += cash[m]
        leaf[st.id] = (cost, start, finish)
        leaf_rows[st.id] = (accrual, cash)
        leaf_treatment[st.id] = treatment
        fact_leaf[st.id] = (st.actual_cost, st.actual_start_month, st.actual_finish_month)

    memo: dict[str, tuple[Decimal, int, int]] = {}

    def rollup(sid: str, visiting: frozenset[str]) -> tuple[Decimal, int, int]:
        if sid in leaf:
            return leaf[sid]
        if sid in memo:
            return memo[sid]
        cost, starts, finishes = ZERO, [], []
        for kid in children.get(sid, []):
            if kid in visiting:
                continue                              # защита от цикла в иерархии
            c, s, f = rollup(kid, visiting | {sid})
            cost += c
            starts.append(s)
            finishes.append(f)
        memo[sid] = (cost, min(starts) if starts else 0, max(finishes) if finishes else 0)
        return memo[sid]

    fact_memo: dict[str, tuple[Optional[Decimal], Optional[int], Optional[int]]] = {}

    def rollup_fact(sid: str, visiting: frozenset[str]):
        """Свёртка факта: Σ ненулевых стоимостей потомков, min/max факт-дат (None — нет факта)."""
        if sid in fact_leaf:
            return fact_leaf[sid]
        if sid in fact_memo:
            return fact_memo[sid]
        costs, starts, finishes = [], [], []
        for kid in children.get(sid, []):
            if kid in visiting:
                continue
            c, s, f = rollup_fact(kid, visiting | {sid})
            if c is not None:
                costs.append(c)
            if s is not None:
                starts.append(s)
            if f is not None:
                finishes.append(f)
        out = (sum(costs, ZERO) if costs else None,
               min(starts) if starts else None,
               max(finishes) if finishes else None)
        fact_memo[sid] = out
        return out

    rows_memo: dict[str, tuple[list[Decimal], list[Decimal]]] = {}

    def rollup_rows(sid: str, visiting: frozenset[str]) -> tuple[list[Decimal], list[Decimal]]:
        """Свёртка помесячных рядов группы: суммы рядов потомков."""
        if sid in leaf_rows:
            return leaf_rows[sid]
        if sid in rows_memo:
            return rows_memo[sid]
        acc, cash = zeros(n), zeros(n)
        for kid in children.get(sid, []):
            if kid in visiting:
                continue
            a, c = rollup_rows(kid, visiting | {sid})
            for m in range(n):
                acc[m] += a[m]
                cash[m] += c[m]
        rows_memo[sid] = (acc, cash)
        return rows_memo[sid]

    treat_memo: dict[str, str] = {}

    def rollup_treatment(sid: str, visiting: frozenset[str]) -> str:
        """Трактовка группы — общая трактовка потомков; при смешении «mixed».

        Приписывать группе трактовку одного из потомков нельзя: она определяет, куда
        стоимость попадёт в отчётах, и смешанной группе такого ответа просто нет.
        """
        if sid in leaf_treatment:
            return leaf_treatment[sid]
        if sid in treat_memo:
            return treat_memo[sid]
        kinds = set()
        for kid in children.get(sid, []):
            if kid in visiting:
                continue
            t = rollup_treatment(kid, visiting | {sid})
            if t != "none":
                kinds.add(t)
        treat_memo[sid] = kinds.pop() if len(kinds) == 1 else ("mixed" if kinds else "none")
        return treat_memo[sid]

    rows = []
    for st in cal.stages:
        cost, start, finish = rollup(st.id, frozenset())
        a_cost, a_start, a_finish = rollup_fact(st.id, frozenset())
        accrual, cash = rollup_rows(st.id, frozenset())
        cost_var = (a_cost - cost) if a_cost is not None else None
        sched_var = (a_finish - finish) if a_finish is not None else None
        rows.append(StageBudget(
            id=st.id, name=st.name, kind=st.kind, start_month=start, finish_month=finish,
            cost=cost, actual_start_month=a_start, actual_finish_month=a_finish,
            actual_cost=a_cost, cost_variance=cost_var, schedule_variance_months=sched_var,
            monthly=accrual, monthly_cash=cash,
            treatment=rollup_treatment(st.id, frozenset())))
    total = sum((c for c, _, _ in leaf.values()), ZERO)
    fact_costs = [c for c, _, _ in fact_leaf.values() if c is not None]
    actual_total = sum(fact_costs, ZERO) if fact_costs else None

    # Разбивка по трактовке считается по листьям: только они несут стоимость.
    by_treatment = {"expense": ZERO, "deferred": ZERO, "asset": ZERO}
    for sid, (cost, _, _) in leaf.items():
        t = leaf_treatment[sid]
        if t in by_treatment:
            by_treatment[t] += cost

    cum, cum_cash = cumulative(monthly), cumulative(monthly_cash)
    return Budget(
        stages=rows, monthly=monthly, total=total, actual_total=actual_total,
        monthly_cash=monthly_cash, cumulative=cum, cumulative_cash=cum_cash,
        payables=[cum[t] - cum_cash[t] for t in range(n)],
        expense_total=by_treatment["expense"], deferred_total=by_treatment["deferred"],
        asset_total=by_treatment["asset"],
    )
