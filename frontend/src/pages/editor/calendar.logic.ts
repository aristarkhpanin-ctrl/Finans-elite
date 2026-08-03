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

/**
 * Трактовка стоимости этапа в отчётах — то, ради чего смета вообще нужна финансисту:
 * одна и та же сумма попадёт либо в издержки периода, либо в расходы будущих периодов,
 * либо в основные средства, и прибыль с налогом будут разными.
 */
export type Treatment = "expense" | "deferred" | "asset" | "mixed" | "none";

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
  // Финансовый разрез этапа: освоение и оплата по месяцам + трактовка.
  monthly: number[];
  monthlyCash: number[];
  treatment: Treatment;
}

export interface Budget {
  rows: BudgetRow[];
  monthly: number[];        // освоение (начисление) по месяцам
  monthlyCash: number[];    // оплата по месяцам (со сдвигом на отсрочку ресурсов)
  cumulative: number[];     // накопленное освоение
  cumulativeCash: number[]; // накопленная оплата
  payables: number[];       // начислено − оплачено = обязательства перед подрядчиками
  total: number;
  actualTotal: number | null;
  // Разбивка сметы по трактовке (Σ = total).
  expenseTotal: number;
  deferredTotal: number;
  assetTotal: number;
}

/**
 * Помесячная оплата этапа: график начисления со сдвигом на отсрочку каждого ресурса.
 * Зеркало `_payment_graph` движка. Прямая стоимость (без ресурсов) платится без сдвига.
 */
function paymentGraph(stage: Stage, cost: number, graph: [number, number][],
                      byRes: Map<string, Resource>, n: number): number[] {
  const out = new Array(Math.max(0, n)).fill(0);
  if (stage.resources && stage.resources.length) {
    for (const sr of stage.resources) {
      const r = byRes.get(sr.resource_id);
      if (!r) continue;
      const costR = num(sr.quantity) * num(r.unit_price);
      for (const [m, frac] of graph) {
        const pay = m + (r.payment_delay_months ?? 0);
        if (pay >= 0 && pay < n) out[pay] += costR * frac;
      }
    }
  } else {
    for (const [m, frac] of graph) {
      if (m >= 0 && m < n) out[m] += cost * frac;
    }
  }
  return out;
}

/** График начисления стоимости этапа: пары (месяц, доля). Зеркало `_schedule` движка. */
function accrualGraph(start: number, dur: number, timing: string): [number, number][] {
  if (timing === "on_finish") return [[start + dur - 1, 1]];
  const per = 1 / dur;
  return Array.from({ length: dur }, (_, k) => [start + k, per] as [number, number]);
}

const cumsum = (xs: number[]): number[] => {
  let acc = 0;
  return xs.map((x) => (acc += x));
};

/** Смета: строки (листья + свёрнутые группы), помесячный график начисления, итог. */
export function computeBudget(stages: Stage[], resources: Resource[], n: number): Budget {
  const byRes = new Map(resources.map((r) => [r.id, r]));
  const groups = groupIds(stages);
  const sched = resolveSchedule(stages);
  const monthly = new Array(Math.max(0, n)).fill(0);
  const monthlyCash = new Array(Math.max(0, n)).fill(0);
  const leaf = new Map<string, { cost: number; start: number; finish: number }>();
  const leafRows = new Map<string, { accrual: number[]; cash: number[] }>();
  const leafTreatment = new Map<string, Treatment>();

  for (const st of stages) {
    if (groups.has(st.id)) continue;
    const { start, finish } = sched.get(st.id)!;
    const kind = (st.kind ?? "expense") as StageKind;
    const accrual = new Array(Math.max(0, n)).fill(0);
    let cash = new Array(Math.max(0, n)).fill(0);
    let cost = 0;
    let treatment: Treatment = "none";
    if (kind === "expense") {
      cost = stageCost(st, byRes);
      const dur = Math.max(1, st.duration_months ?? 1);
      const graph = accrualGraph(start, dur, st.cost_timing ?? "uniform");
      for (const [m, frac] of graph) {
        if (m >= 0 && m < n) accrual[m] += cost * frac;
      }
      cash = paymentGraph(st, cost, graph, byRes, n);
      treatment = (st.amortize_months ?? 0) > 0 ? "deferred" : "expense";
    } else if (kind === "asset") {
      cost = stageCost(st, byRes);
      // Актив ставится разово в месяц финиша; отсрочки ресурсов машинерия активов
      // не применяет, поэтому оплата совпадает с освоением (как в движке).
      if (finish >= 0 && finish < n) {
        accrual[finish] += cost;
        cash[finish] += cost;
      }
      treatment = "asset";
    }
    for (let m = 0; m < n; m++) {
      monthly[m] += accrual[m];
      monthlyCash[m] += cash[m];
    }
    leaf.set(st.id, { cost, start, finish });
    leafRows.set(st.id, { accrual, cash });
    leafTreatment.set(st.id, treatment);
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

  /** Свёртка помесячных рядов группы: суммы рядов потомков. */
  const rollupRows = (id: string, visiting: Set<string>): { accrual: number[]; cash: number[] } => {
    const l = leafRows.get(id);
    if (l) return l;
    const accrual = new Array(Math.max(0, n)).fill(0);
    const cash = new Array(Math.max(0, n)).fill(0);
    for (const kid of children.get(id) ?? []) {
      if (visiting.has(kid)) continue;
      const c = rollupRows(kid, new Set(visiting).add(id));
      for (let m = 0; m < n; m++) {
        accrual[m] += c.accrual[m];
        cash[m] += c.cash[m];
      }
    }
    return { accrual, cash };
  };

  /**
   * Трактовка группы — общая трактовка потомков; при смешении «mixed». Приписывать группе
   * трактовку одного из потомков нельзя: она определяет, куда стоимость попадёт в отчётах.
   */
  const rollupTreatment = (id: string, visiting: Set<string>): Treatment => {
    const l = leafTreatment.get(id);
    if (l) return l;
    const kinds = new Set<Treatment>();
    for (const kid of children.get(id) ?? []) {
      if (visiting.has(kid)) continue;
      const t = rollupTreatment(kid, new Set(visiting).add(id));
      if (t !== "none") kinds.add(t);
    }
    return kinds.size === 1 ? [...kinds][0] : kinds.size ? "mixed" : "none";
  };

  const rows: BudgetRow[] = stages.map((st) => {
    const r = rollup(st.id, new Set());
    const f = rollupFact(st.id, new Set());
    const series = rollupRows(st.id, new Set());
    return {
      id: st.id, name: st.name ?? "", kind: (st.kind ?? "expense") as StageKind, ...r,
      actualCost: f.cost, actualStart: f.start, actualFinish: f.finish,
      costVariance: f.cost !== null ? f.cost - r.cost : null,
      scheduleVariance: f.finish !== null ? f.finish - r.finish : null,
      monthly: series.accrual, monthlyCash: series.cash,
      treatment: rollupTreatment(st.id, new Set()),
    };
  });
  let total = 0;
  for (const v of leaf.values()) total += v.cost;
  const factCosts = [...factLeaf.values()].map((f) => f.cost).filter((c): c is number => c !== null);
  const actualTotal = factCosts.length ? factCosts.reduce((a, b) => a + b, 0) : null;

  // Разбивка по трактовке — по листьям: только они несут стоимость.
  const by: Record<string, number> = { expense: 0, deferred: 0, asset: 0 };
  for (const [id, v] of leaf) {
    const t = leafTreatment.get(id) ?? "none";
    if (t in by) by[t] += v.cost;
  }

  const cumulative = cumsum(monthly);
  const cumulativeCash = cumsum(monthlyCash);
  return {
    rows, monthly, monthlyCash, cumulative, cumulativeCash,
    payables: cumulative.map((v, t) => v - cumulativeCash[t]),
    total, actualTotal,
    expenseTotal: by.expense, deferredTotal: by.deferred, assetTotal: by.asset,
  };
}
