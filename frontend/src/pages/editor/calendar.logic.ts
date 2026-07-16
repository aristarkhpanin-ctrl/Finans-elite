// Чистая логика календарного плана (зеркало calc_core/engine/calendar.py): разрешение
// расписания (связи финиш→старт с защитой от циклов), стоимость этапа и смета — для
// живого предпросмотра (Гантт + бюджет) без обращения к бэкенду.
import type { Resource, Stage, StageKind } from "../../api/model";

const num = (v: string | number | undefined | null): number => {
  const x = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
};

export interface Sched {
  start: number;
  finish: number;
}

/** Эффективные (start, finish) по каждому этапу с учётом предшественников. */
export function resolveSchedule(stages: Stage[]): Map<string, Sched> {
  const byId = new Map(stages.map((s) => [s.id, s]));
  const memo = new Map<string, Sched>();
  const resolve = (id: string, visiting: Set<string>): Sched => {
    const cached = memo.get(id);
    if (cached) return cached;
    const s = byId.get(id)!;
    const dur = Math.max(1, s.duration_months ?? 1);
    const sm = s.start_month ?? 0;
    let start = sm;
    const pred = s.predecessor_id;
    if (pred && byId.has(pred) && !visiting.has(pred)) {
      start = resolve(pred, new Set(visiting).add(id)).finish + sm;
    }
    const res = { start, finish: start + dur };
    memo.set(id, res);
    return res;
  };
  for (const s of stages) resolve(s.id, new Set());
  return memo;
}

/** Идентификаторы этапов-групп (на них ссылаются как на родителя). */
export function groupIds(stages: Stage[]): Set<string> {
  const g = new Set<string>();
  for (const s of stages) if (s.parent_id) g.add(s.parent_id);
  return g;
}

/** Стоимость этапа: Σ(кол-во×цена ресурса) либо прямая cost. */
export function stageCost(stage: Stage, byRes: Map<string, Resource>): number {
  if (stage.resources && stage.resources.length) {
    let t = 0;
    for (const sr of stage.resources) {
      const r = byRes.get(sr.resource_id);
      if (r) t += num(sr.quantity) * num(r.unit_price);
    }
    return t;
  }
  return num(stage.cost);
}

export interface BudgetRow {
  id: string;
  name: string;
  kind: StageKind;
  start: number;
  finish: number;
  cost: number;
  // Актуализация (план-факт, gap 4.6): null — этап не актуализирован.
  actualCost: number | null;
  actualStart: number | null;
  actualFinish: number | null;
  costVariance: number | null;
  scheduleVariance: number | null;
}

export interface Budget {
  rows: BudgetRow[];
  monthly: number[];
  total: number;
  actualTotal: number | null;
}

/** Смета: строки (листья + свёрнутые группы), помесячный график начисления, итог. */
export function computeBudget(stages: Stage[], resources: Resource[], n: number): Budget {
  const byRes = new Map(resources.map((r) => [r.id, r]));
  const groups = groupIds(stages);
  const sched = resolveSchedule(stages);
  const monthly = new Array(Math.max(0, n)).fill(0);
  const leaf = new Map<string, { cost: number; start: number; finish: number }>();

  for (const st of stages) {
    if (groups.has(st.id)) continue;
    const { start, finish } = sched.get(st.id)!;
    const kind = (st.kind ?? "expense") as StageKind;
    let cost = 0;
    if (kind === "expense") {
      cost = stageCost(st, byRes);
      const dur = Math.max(1, st.duration_months ?? 1);
      if (st.cost_timing === "on_finish") {
        const m = start + dur - 1;
        if (m >= 0 && m < n) monthly[m] += cost;
      } else {
        const per = cost / dur;
        for (let k = 0; k < dur; k++) {
          const m = start + k;
          if (m >= 0 && m < n) monthly[m] += per;
        }
      }
    } else if (kind === "asset") {
      cost = stageCost(st, byRes);
      if (finish >= 0 && finish < n) monthly[finish] += cost;
    }
    leaf.set(st.id, { cost, start, finish });
  }

  const children = new Map<string, string[]>();
  for (const s of stages) {
    if (s.parent_id) {
      const arr = children.get(s.parent_id) ?? [];
      arr.push(s.id);
      children.set(s.parent_id, arr);
    }
  }
  const rollup = (id: string, visiting: Set<string>): { cost: number; start: number; finish: number } => {
    const l = leaf.get(id);
    if (l) return l;
    let cost = 0;
    const starts: number[] = [];
    const finishes: number[] = [];
    for (const kid of children.get(id) ?? []) {
      if (visiting.has(kid)) continue;
      const c = rollup(kid, new Set(visiting).add(id));
      cost += c.cost;
      starts.push(c.start);
      finishes.push(c.finish);
    }
    return { cost, start: starts.length ? Math.min(...starts) : 0, finish: finishes.length ? Math.max(...finishes) : 0 };
  };

  // Факт по листьям (план-факт): null — не актуализирован.
  const optNum = (v: string | number | undefined | null): number | null =>
    v === null || v === undefined || v === "" ? null : num(v);
  const factLeaf = new Map<string, { cost: number | null; start: number | null; finish: number | null }>();
  for (const st of stages) {
    if (groups.has(st.id)) continue;
    factLeaf.set(st.id, {
      cost: optNum(st.actual_cost),
      start: optNum(st.actual_start_month),
      finish: optNum(st.actual_finish_month),
    });
  }
  const rollupFact = (id: string, visiting: Set<string>): { cost: number | null; start: number | null; finish: number | null } => {
    const l = factLeaf.get(id);
    if (l) return l;
    const costs: number[] = [];
    const starts: number[] = [];
    const finishes: number[] = [];
    for (const kid of children.get(id) ?? []) {
      if (visiting.has(kid)) continue;
      const c = rollupFact(kid, new Set(visiting).add(id));
      if (c.cost !== null) costs.push(c.cost);
      if (c.start !== null) starts.push(c.start);
      if (c.finish !== null) finishes.push(c.finish);
    }
    return {
      cost: costs.length ? costs.reduce((a, b) => a + b, 0) : null,
      start: starts.length ? Math.min(...starts) : null,
      finish: finishes.length ? Math.max(...finishes) : null,
    };
  };

  const rows: BudgetRow[] = stages.map((st) => {
    const r = rollup(st.id, new Set());
    const f = rollupFact(st.id, new Set());
    return {
      id: st.id, name: st.name ?? "", kind: (st.kind ?? "expense") as StageKind, ...r,
      actualCost: f.cost, actualStart: f.start, actualFinish: f.finish,
      costVariance: f.cost !== null ? f.cost - r.cost : null,
      scheduleVariance: f.finish !== null ? f.finish - r.finish : null,
    };
  });
  let total = 0;
  for (const v of leaf.values()) total += v.cost;
  const factCosts = [...factLeaf.values()].map((f) => f.cost).filter((c): c is number => c !== null);
  const actualTotal = factCosts.length ? factCosts.reduce((a, b) => a + b, 0) : null;
  return { rows, monthly, total, actualTotal };
}
