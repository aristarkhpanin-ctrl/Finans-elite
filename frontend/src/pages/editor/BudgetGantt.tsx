import React, { useMemo, useState } from "react";
import { periodChunks } from "../../aggregate";
import type { Resource, Stage } from "../../api/model";
import { fmtMoney } from "../../format";
import { applyDrag, computeBudget, resolveSchedule } from "./calendar.logic";
import type { Budget, BudgetRow, DragMode, Sched, Treatment } from "./calendar.logic";

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
  stage: Stage;            // исходный этап — источник правки при перетаскивании
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
      out.push({ row, stage: s, depth, hasKids: children.length > 0 });
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

interface DragState {
  id: string;
  mode: DragMode;
  fromX: number;
  delta: number;           // сдвиг в целых месяцах
}

/** Длина «уса» связи от края полосы до поворота, px. */
const STUB = 9;

/**
 * Путь связи «финиш → старт» между полосами. Если преемник начинается правее финиша
 * предшественника — прямой путь в три сегмента; если левее или вплотную (нулевой лаг,
 * перекрытие) — обход между строками, иначе линия легла бы поверх самих полос.
 */
export function linkPath(x1: number, y1: number, x2: number, y2: number): string {
  return x2 >= x1 + STUB
    ? `M${x1},${y1} H${x1 + STUB} V${y2} H${x2 - 3}`
    : `M${x1},${y1} H${x1 + STUB} V${(y1 + y2) / 2} H${x2 - STUB} V${y2} H${x2 - 3}`;
}

interface Props {
  n: number;
  startDate?: string;          // дата старта проекта — для календарных подписей колонок
  stages: Stage[];
  resources: Resource[];
  budget: Budget;
  sched: Map<string, Sched>;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  /** Правка сроков перетаскиванием; без обработчика диаграмма только для чтения. */
  onStageChange?: (id: string, patch: Partial<Stage>) => void;
}

export function BudgetGantt({ n, startDate, stages, resources, budget, sched,
                             selectedId, onSelect, onStageChange }: Props) {
  const [scale, setScale] = useState<Scale>(n <= 24 ? "month" : n <= 72 ? "quarter" : "year");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showCash, setShowCash] = useState(true);
  const [drag, setDrag] = useState<DragState | null>(null);

  const draggable = !!onStageChange;

  /** Сроки этапа после перетаскивания (без правки модели — только предпросмотр). */
  const dragged = (st: Stage): Stage =>
    (!drag || drag.id !== st.id || drag.delta === 0)
      ? st
      : { ...st, ...applyDrag(st, drag.mode, drag.delta) };

  // Во время перетаскивания смета и расписание считаются по предпросмотру: деньги внизу
  // должны меняться вместе с полосой, иначе сдвиг этапа выглядит как чисто календарная
  // правка — а он двигает и освоение, и оплату.
  const liveStages = useMemo(
    () => (drag ? stages.map(dragged) : stages), [stages, drag]);   // eslint-disable-line react-hooks/exhaustive-deps
  const liveSched = useMemo(
    () => (drag ? resolveSchedule(liveStages) : sched), [drag, liveStages, sched]);
  const liveBudget = useMemo(
    () => (drag ? computeBudget(liveStages, resources, n) : budget),
    [drag, liveStages, resources, n, budget]);

  const rowsById = useMemo(
    () => new Map(liveBudget.rows.map((r) => [r.id, r])), [liveBudget.rows]);
  const nodes = useMemo(
    () => flatten(stages, rowsById, collapsed), [stages, rowsById, collapsed]);

  // Горизонт диаграммы: месяцы проекта плюс этапы, выходящие за него (их видно, но
  // деньги за горизонтом в отчёты не попадают — об этом предупреждает подпись ниже).
  const maxFinish = Math.max(0, ...[...liveSched.values()].map((s) => s.finish));
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

  // ── Перетаскивание ─────────────────────────────────────────────────────────
  const pxPerMonth = colW / per;

  const onDragStart = (e: React.PointerEvent, st: Stage, mode: DragMode) => {
    if (!draggable) return;
    e.preventDefault();
    e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    setDrag({ id: st.id, mode, fromX: e.clientX, delta: 0 });
  };

  const onDragMove = (e: React.PointerEvent) => {
    if (!drag) return;
    // Шаг — целый месяц при любом масштабе: модель месячная, дробных сроков не бывает.
    const delta = Math.round((e.clientX - drag.fromX) / pxPerMonth);
    if (delta !== drag.delta) setDrag({ ...drag, delta });
  };

  const onDragEnd = (e: React.PointerEvent) => {
    if (!drag) return;
    (e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
    const st = stages.find((x) => x.id === drag.id);
    if (st && drag.delta !== 0) {
      const next = dragged(st);
      const patch: Partial<Stage> = {};
      if (next.start_month !== st.start_month) patch.start_month = next.start_month;
      if (next.duration_months !== st.duration_months) patch.duration_months = next.duration_months;
      if (Object.keys(patch).length) onStageChange?.(drag.id, patch);
    }
    setDrag(null);
  };

  // ── Связи-предшественники ──────────────────────────────────────────────────
  const indexOf = new Map(nodes.map((nd, i) => [nd.row.id, i]));
  const parentOf = new Map(stages.map((st) => [st.id, st.parent_id ?? null]));

  /** Ближайший видимый предок (этап внутри свёрнутой группы «переезжает» на неё). */
  const visibleRow = (id: string | null | undefined): number | undefined => {
    let cur = id ?? null;
    const seen = new Set<string>();
    while (cur && !seen.has(cur)) {
      const i = indexOf.get(cur);
      if (i !== undefined) return i;
      seen.add(cur);
      cur = parentOf.get(cur) ?? null;
    }
    return undefined;
  };

  const yOf = (i: number) => i * ROW_H + ROW_H / 2;

  /** Пути связей «финиш → старт»; связь внутри одной строки не рисуется. */
  const links = stages.flatMap((st) => {
    const from = visibleRow(st.predecessor_id);
    const to = visibleRow(st.id);
    if (from === undefined || to === undefined || from === to) return [];
    const pred = liveSched.get(st.predecessor_id!);
    const self = liveSched.get(st.id);
    if (!pred || !self) return [];
    const d = linkPath(xOf(pred.finish), yOf(from), xOf(self.start), yOf(to));
    return [{ key: `${st.predecessor_id}->${st.id}`, d }];
  });

  const lanes: [string, number[], string][] = [
    ["Освоение", foldFlow(liveBudget.monthly), "Начисление стоимости по графику работ"],
    ["Оплата", foldFlow(liveBudget.monthlyCash), "Отток денег с учётом отсрочек по ресурсам"],
    ["Оплачено нарастающим", foldLevel(liveBudget.cumulativeCash), "Сколько денег ушло с начала проекта"],
    ["Не оплачено", foldLevel(liveBudget.payables), "Обязательства перед подрядчиками (кредиторка)"],
  ];
  const maxFlow = Math.max(1, ...foldFlow(liveBudget.monthly), ...foldFlow(liveBudget.monthlyCash));

  return (
    <div className="bg-gantt">
      <div className="bg-gantt__toolbar">
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

      {draggable && (
        <div className="field-note" style={{ marginBottom: 8 }}>
          Полосы можно перетаскивать: тело — сдвиг сроков, края — начало и длительность.
          Деньги внизу пересчитываются на лету, поэтому сдвиг этапа сразу видно в графике
          освоения и оплаты. Сроки групп — свёртка потомков, поэтому тянутся только они.
        </div>
      )}

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
            const share = liveBudget.total > 0 ? row.cost / liveBudget.total : 0;
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
              {/* Связи «финиш → старт». Мышь их не ловит — тянуть надо полосы. */}
              {links.length > 0 && (
                <svg className="bg-gantt__links" width={width} height={nodes.length * ROW_H}>
                  <defs>
                    <marker id="bgGanttArrow" markerWidth="7" markerHeight="7"
                            refX="6" refY="3" orient="auto">
                      <path d="M0,0 L6,3 L0,6 Z" fill="var(--muted)" />
                    </marker>
                  </defs>
                  {links.map((l) => (
                    <path key={l.key} className="bg-gantt__link" d={l.d}
                          markerEnd="url(#bgGanttArrow)" />
                  ))}
                </svg>
              )}
              {nodes.map(({ row, hasKids, stage }) => {
                const cashSpan = span(row.monthlyCash);
                const tr = TREATMENT[row.treatment];
                // Группу перетаскивать нельзя: её сроки — свёртка потомков, тянуть надо их.
                const canDrag = draggable && !hasKids;
                const isDragging = drag?.id === row.id;
                return (
                  <div key={row.id} style={{ height: ROW_H }}
                       className={"bg-gantt__track" + (selectedId === row.id ? " bg-gantt__track--sel" : "")}
                       onClick={() => onSelect?.(row.id)}>
                    <div
                      className={"bg-gantt__bar" + (hasKids ? " bg-gantt__bar--group" : "")
                                 + (canDrag ? " bg-gantt__bar--drag" : "")
                                 + (isDragging ? " bg-gantt__bar--active" : "")}
                      style={{
                        left: xOf(row.start),
                        width: Math.max(4, xOf(row.finish) - xOf(row.start)),
                        background: tr.color,
                      }}
                      onPointerDown={canDrag ? (e) => onDragStart(e, stage, "move") : undefined}
                      onPointerMove={canDrag ? onDragMove : undefined}
                      onPointerUp={canDrag ? onDragEnd : undefined}
                      onPointerCancel={canDrag ? onDragEnd : undefined}
                      title={`${row.name || row.id} · мес. ${row.start}–${row.finish}`
                             + ` · ${tr.label} · ${fmtMoney(row.cost)}`
                             + (canDrag ? "\nПотяните, чтобы сдвинуть сроки" : "")
                             + (hasKids ? "\nСроки группы — свёртка потомков" : "")}
                    >
                      {canDrag && (
                        <>
                          <span className="bg-gantt__handle bg-gantt__handle--l"
                                title="Тянуть — сдвинуть начало (финиш на месте)"
                                onPointerDown={(e) => onDragStart(e, stage, "start")}
                                onPointerMove={onDragMove}
                                onPointerUp={onDragEnd}
                                onPointerCancel={onDragEnd} />
                          <span className="bg-gantt__handle bg-gantt__handle--r"
                                title="Тянуть — изменить длительность"
                                onPointerDown={(e) => onDragStart(e, stage, "end")}
                                onPointerMove={onDragMove}
                                onPointerUp={onDragEnd}
                                onPointerCancel={onDragEnd} />
                        </>
                      )}
                    </div>
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
                    {row.cost > 0 && !isDragging && (
                      <span className="bg-gantt__cost" style={{ left: xOf(row.finish) + 6 }}>
                        {fmtMoney(row.cost)}
                      </span>
                    )}
                    {isDragging && (
                      <span className="bg-gantt__tip" style={{ left: xOf(row.finish) + 8 }}>
                        мес. {row.start}–{row.finish}
                        {stage.predecessor_id
                          ? ` · лаг ${liveStages.find((x) => x.id === row.id)?.start_month ?? 0} мес.`
                          : ""}
                        {" · "}{fmtMoney(row.cost)}
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
