import { useMemo, useState } from "react";
import { periodChunks } from "../../aggregate";
import type { Stage } from "../../api/model";
import { fmtMoney } from "../../format";
import type { Budget, BudgetRow, Sched, Treatment } from "./calendar.logic";

/**
 * Бюджетная диаграмма Ганта — календарный план глазами финансового директора.
 *
 * Отличия от обычного Гантта руководителя проекта (они же — смысл этого экрана):
 *
 * 1. **Полоса красится по трактовке стоимости, а не по типу этапа.** Цвет отвечает на
 *    вопрос «куда эти деньги попадут в отчётах»: издержки периода, расходы будущих
 *    периодов или основные средства. От этого зависят прибыль и налог, и именно это
 *    отличает бюджетный план от плана работ.
 * 2. **У каждого этапа две полосы: освоение и оплата.** Работы идут по графику, а деньги
 *    уходят с отсрочкой; расстояние между полосами — и есть кредиторка перед подрядчиком.
 * 3. **Нижняя панель — деньги по периодам**, а не загрузка ресурсов: освоение, оплата,
 *    накопленная оплата и неоплаченные обязательства.
 *
 * Все числа берутся из готовой сметы (`calendar.logic`, зеркало движка) — компонент
 * ничего не пересчитывает, поэтому картинка не может разойтись с расчётом.
 */

type Scale = "month" | "quarter" | "year";

const MONTHS_PER: Record<Scale, number> = { month: 1, quarter: 3, year: 12 };
const COL_W: Record<Scale, number> = { month: 36, quarter: 52, year: 68 };
const SCALES: [Scale, string][] = [["month", "Месяц"], ["quarter", "Квартал"], ["year", "Год"]];

const ROW_H = 30;      // высота строки (левая таблица и диаграмма обязаны совпадать)
const LANE_H = 26;     // высота строки нижней денежной панели

/** Трактовка → подпись и цвет полосы (легенда диаграммы). */
const TREATMENT: Record<Treatment, { label: string; short: string; color: string }> = {
  expense: { label: "Издержки периода", short: "Издержки", color: "var(--chart-3)" },
  deferred: { label: "Расходы будущих периодов", short: "РБП", color: "var(--chart-5)" },
  asset: { label: "Капитальные вложения", short: "Актив", color: "var(--chart-1)" },
  mixed: { label: "Смешанная группа", short: "Смешанная", color: "var(--chart-7)" },
  none: { label: "Без стоимости", short: "—", color: "var(--border-strong)" },
};

const MONTH_NAMES = ["янв", "фев", "мар", "апр", "май", "июн",
                     "июл", "авг", "сен", "окт", "ноя", "дек"];

interface Node {
  row: BudgetRow;
  depth: number;
  hasKids: boolean;
}

/** Дерево этапов в порядке обхода (родитель раньше потомков), свёрнутые ветви скрыты. */
function flatten(stages: Stage[], rows: Map<string, BudgetRow>,
                 collapsed: Set<string>): Node[] {
  const known = new Set(stages.map((s) => s.id));
  const kids = new Map<string, Stage[]>();
  const roots: Stage[] = [];
  for (const s of stages) {
    const parent = s.parent_id && known.has(s.parent_id) ? s.parent_id : null;
    if (!parent) { roots.push(s); continue; }
    const list = kids.get(parent);
    if (list) list.push(s); else kids.set(parent, [s]);
  }
  const out: Node[] = [];
  const walk = (list: Stage[], depth: number, seen: Set<string>) => {
    for (const s of list) {
      if (seen.has(s.id)) continue;      // защита от цикла в иерархии
      const row = rows.get(s.id);
      if (!row) continue;
      const children = kids.get(s.id) ?? [];
      out.push({ row, depth, hasKids: children.length > 0 });
      if (children.length && !collapsed.has(s.id)) {
        walk(children, depth + 1, new Set(seen).add(s.id));
      }
    }
  };
  walk(roots, 0, new Set());
  return out;
}

/** Первый и последний месяц с ненулевым значением ряда (null — ряд пуст). */
function span(series: number[]): [number, number] | null {
  let first = -1;
  let last = -1;
  for (let t = 0; t < series.length; t++) {
    if (Math.abs(series[t]) > 1e-9) {
      if (first < 0) first = t;
      last = t;
    }
  }
  return first < 0 ? null : [first, last + 1];
}

interface Props {
  n: number;
  startDate?: string;          // дата старта проекта — для календарных подписей колонок
  stages: Stage[];
  budget: Budget;
  sched: Map<string, Sched>;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}

export function BudgetGantt({ n, startDate, stages, budget, sched, selectedId, onSelect }: Props) {
  const [scale, setScale] = useState<Scale>(n <= 24 ? "month" : n <= 72 ? "quarter" : "year");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showCash, setShowCash] = useState(true);

  const rowsById = useMemo(
    () => new Map(budget.rows.map((r) => [r.id, r])), [budget.rows]);
  const nodes = useMemo(
    () => flatten(stages, rowsById, collapsed), [stages, rowsById, collapsed]);

  // Горизонт диаграммы: месяцы проекта плюс этапы, выходящие за него (их видно, но
  // деньги за горизонтом в отчёты не попадают — об этом предупреждает подпись ниже).
  const maxFinish = Math.max(0, ...[...sched.values()].map((s) => s.finish));
  const horizon = Math.max(1, n, maxFinish);
  const overrun = maxFinish > n;

  const per = MONTHS_PER[scale];
  const colW = COL_W[scale];
  const chunks = periodChunks(horizon, scale);
  const width = chunks.length * colW;
  const xOf = (month: number) => (month / per) * colW;

  const toggle = (id: string) =>
    setCollapsed((c) => {
      const next = new Set(c);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });

  /** Подпись колонки: календарная, если известна дата старта, иначе номер периода. */
  const label = (a: number): { top: string; bottom: string } => {
    if (!startDate) {
      const i = Math.floor(a / per) + 1;
      return scale === "month" ? { top: "", bottom: `М${i}` }
        : scale === "quarter" ? { top: "", bottom: `К${i}` } : { top: "", bottom: `Год ${i}` };
    }
    const d = new Date(startDate);
    const m = d.getMonth() + a;
    const year = d.getFullYear() + Math.floor(m / 12);
    const mm = ((m % 12) + 12) % 12;
    if (scale === "year") return { top: "", bottom: String(year) };
    if (scale === "quarter") return { top: String(year), bottom: `К${Math.floor(mm / 3) + 1}` };
    return { top: mm === 0 || a === 0 ? String(year) : "", bottom: MONTH_NAMES[mm] };
  };

  // Свёртка денежных рядов под масштаб: потоки суммируются, уровни берутся на конец
  // периода (то же правило, что в агрегации отчётов — иначе строки будут о разном).
  const foldFlow = (s: number[]) => chunks.map(([a, b]) => {
    let acc = 0;
    for (let t = a; t < b; t++) acc += s[t] ?? 0;
    return acc;
  });
  const foldLevel = (s: number[]) => chunks.map(([, b]) => s[b - 1] ?? 0);

  const lanes: [string, number[], string][] = [
    ["Освоение", foldFlow(budget.monthly), "Начисление стоимости по графику работ"],
    ["Оплата", foldFlow(budget.monthlyCash), "Отток денег с учётом отсрочек по ресурсам"],
    ["Оплачено нарастающим", foldLevel(budget.cumulativeCash), "Сколько денег ушло с начала проекта"],
    ["Не оплачено", foldLevel(budget.payables), "Обязательства перед подрядчиками (кредиторка)"],
  ];
  const maxFlow = Math.max(1, ...foldFlow(budget.monthly), ...foldFlow(budget.monthlyCash));

  return (
    <div className="bg-gantt">
      <div className="bg-gantt__bar">
        <div className="seg seg--sm">
          {SCALES.map(([key, text]) => (
            <button key={key} type="button"
                    className={"seg__btn" + (scale === key ? " seg__btn--active" : "")}
                    onClick={() => setScale(key)}>
              {text}
            </button>
          ))}
        </div>
        <label className="bg-gantt__toggle">
          <input type="checkbox" checked={showCash} onChange={(e) => setShowCash(e.target.checked)} />
          Показывать оплату
        </label>
        <div className="bg-gantt__legend">
          {(["expense", "deferred", "asset"] as Treatment[]).map((t) => (
            <span className="bg-gantt__lg" key={t}>
              <i style={{ background: TREATMENT[t].color }} />{TREATMENT[t].label}
            </span>
          ))}
          {showCash && (
            <span className="bg-gantt__lg"><i className="bg-gantt__lg--cash" />Период оплаты</span>
          )}
        </div>
      </div>

      <div className="bg-gantt__body">
        {/* Левая таблица — колонки финансиста: смета, доля, отклонение факта */}
        <div className="bg-gantt__grid">
          <div className="bg-gantt__head" style={{ height: ROW_H * 2 }}>
            <div className="bg-gantt__cell bg-gantt__cell--name">Этап</div>
            <div className="bg-gantt__cell">Трактовка</div>
            <div className="bg-gantt__cell bg-gantt__cell--num">Смета</div>
            <div className="bg-gantt__cell bg-gantt__cell--num">Доля</div>
            <div className="bg-gantt__cell bg-gantt__cell--num">Δ факт</div>
          </div>
          {nodes.map(({ row, depth, hasKids }) => {
            const share = budget.total > 0 ? row.cost / budget.total : 0;
            const dv = row.costVariance;
            return (
              <div key={row.id} style={{ height: ROW_H }}
                   className={"bg-gantt__row" + (selectedId === row.id ? " bg-gantt__row--sel" : "")}
                   onClick={() => onSelect?.(row.id)}>
                <div className="bg-gantt__cell bg-gantt__cell--name"
                     style={{ paddingLeft: 8 + depth * 14 }}>
                  {hasKids ? (
                    <button type="button" className="bg-gantt__tw"
                            onClick={(e) => { e.stopPropagation(); toggle(row.id); }}>
                      {collapsed.has(row.id) ? "▸" : "▾"}
                    </button>
                  ) : <span className="bg-gantt__tw bg-gantt__tw--empty" />}
                  <span className="bg-gantt__nm">{row.name || row.id}</span>
                </div>
                <div className="bg-gantt__cell">
                  <span className="bg-gantt__chip" style={{ background: TREATMENT[row.treatment].color }}>
                    {TREATMENT[row.treatment].short}
                  </span>
                </div>
                <div className="bg-gantt__cell bg-gantt__cell--num">
                  {row.cost ? fmtMoney(row.cost) : "—"}
                </div>
                <div className="bg-gantt__cell bg-gantt__cell--num">
                  {share > 0 ? (share * 100).toFixed(1).replace(".", ",") + "%" : "—"}
                </div>
                <div className={"bg-gantt__cell bg-gantt__cell--num"
                                + (dv === null ? "" : dv > 0 ? " tone--risk" : dv < 0 ? " tone--ok" : "")}>
                  {dv === null ? "—" : (dv > 0 ? "+" : "") + fmtMoney(dv)}
                </div>
              </div>
            );
          })}
          {/* Подписи денежной панели — выровнены со строками справа */}
          <div className="bg-gantt__lanehead" style={{ height: LANE_H }}>Деньги по периодам</div>
          {lanes.map(([name, , hint]) => (
            <div className="bg-gantt__lanelabel" key={name} style={{ height: LANE_H }} title={hint}>
              {name}
            </div>
          ))}
        </div>

        {/* Диаграмма */}
        <div className="bg-gantt__chart fe-scroll">
          <div style={{ width, position: "relative" }}>
            {/* Шапка периодов */}
            <div className="bg-gantt__timehead" style={{ height: ROW_H * 2 }}>
              {chunks.map(([a], i) => {
                const l = label(a);
                return (
                  <div className="bg-gantt__col" key={i} style={{ width: colW }}>
                    <span className="bg-gantt__colTop">{l.top}</span>
                    <span className="bg-gantt__colBottom">{l.bottom}</span>
                  </div>
                );
              })}
            </div>

            {/* Полосы этапов */}
            <div style={{ position: "relative" }}>
              {chunks.map((_, i) => (
                <div className="bg-gantt__gridline" key={i}
                     style={{ left: i * colW, height: nodes.length * ROW_H }} />
              ))}
              {n < horizon && (
                <div className="bg-gantt__beyond"
                     style={{ left: xOf(n), width: xOf(horizon) - xOf(n),
                              height: nodes.length * ROW_H }} />
              )}
              {nodes.map(({ row, hasKids }) => {
                const cashSpan = span(row.monthlyCash);
                const tr = TREATMENT[row.treatment];
                return (
                  <div key={row.id} style={{ height: ROW_H }}
                       className={"bg-gantt__track" + (selectedId === row.id ? " bg-gantt__track--sel" : "")}
                       onClick={() => onSelect?.(row.id)}>
                    <div
                      className={"bg-gantt__bar" + (hasKids ? " bg-gantt__bar--group" : "")}
                      style={{
                        left: xOf(row.start),
                        width: Math.max(4, xOf(row.finish) - xOf(row.start)),
                        background: tr.color,
                      }}
                      title={`${row.name || row.id} · мес. ${row.start}–${row.finish}`
                             + ` · ${tr.label} · ${fmtMoney(row.cost)}`}
                    />
                    {showCash && cashSpan && (
                      <div className="bg-gantt__cash"
                           style={{ left: xOf(cashSpan[0]),
                                    width: Math.max(4, xOf(cashSpan[1]) - xOf(cashSpan[0])) }}
                           title={`Оплата: мес. ${cashSpan[0]}–${cashSpan[1]}`} />
                    )}
                    {row.actualFinish !== null && row.actualStart !== null && (
                      <div className="bg-gantt__fact"
                           style={{ left: xOf(row.actualStart),
                                    width: Math.max(4, xOf(row.actualFinish) - xOf(row.actualStart)) }}
                           title={`Факт: мес. ${row.actualStart}–${row.actualFinish}`} />
                    )}
                    {row.cost > 0 && (
                      <span className="bg-gantt__cost" style={{ left: xOf(row.finish) + 6 }}>
                        {fmtMoney(row.cost)}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Деньги по периодам */}
            <div className="bg-gantt__lanehead" style={{ height: LANE_H }} />
            {lanes.map(([name, values], li) => (
              <div className="bg-gantt__lane" key={name} style={{ height: LANE_H }}>
                {values.map((v, i) => (
                  <div className="bg-gantt__laneCell" key={i} style={{ width: colW }}
                       title={`${name}: ${fmtMoney(v)}`}>
                    {li < 2 && Math.abs(v) > 1e-9 && (
                      <span className="bg-gantt__laneFill"
                            style={{ height: `${Math.min(100, (Math.abs(v) / maxFlow) * 100)}%`,
                                     background: li === 0 ? "var(--chart-3)" : "var(--chart-2)" }} />
                    )}
                    <span className="bg-gantt__laneNum">
                      {Math.abs(v) > 1e-9 ? fmtMoney(v) : ""}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      {overrun && (
        <div className="field-note field-note--warn" style={{ marginTop: 10 }}>
          Часть этапов выходит за горизонт проекта ({n} мес.). На диаграмме они видны
          целиком, но в отчёты попадают только суммы внутри горизонта — смета и графики
          показывают именно их.
        </div>
      )}
    </div>
  );
}
