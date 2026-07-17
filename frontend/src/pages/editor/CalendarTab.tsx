import type {
  CalendarPlan,
  InvestmentPlan,
  Product,
  Resource,
  Stage,
  StageKind,
} from "../../api/model";
import { EField, ESelect } from "../../components/EditorField";
import { IconTrash } from "../../components/icons";
import { Button } from "../../components/ui";
import { fmtMoney } from "../../format";
import { computeBudget, resolveSchedule, stageCost } from "./calendar.logic";

interface Props {
  n: number;
  investment: InvestmentPlan;
  products: Product[];
  onChange: (iv: InvestmentPlan) => void;
}

const uid = (p: string) => `${p}_${Math.random().toString(36).slice(2, 8)}`;

const KIND: Record<StageKind, { label: string; color: string }> = {
  expense: { label: "Издержки", color: "var(--warn)" },
  asset: { label: "Актив", color: "var(--primary)" },
  production: { label: "Производство", color: "var(--info)" },
};

const KIND_OPTIONS: [string, string][] = [
  ["expense", "Издержки подготовки"],
  ["asset", "Формирует актив"],
  ["production", "Старт производства"],
];

export function CalendarTab({ n, investment, products, onChange }: Props) {
  const cal: CalendarPlan = investment.calendar ?? { stages: [], resources: [] };
  const stages = cal.stages;
  const resources = cal.resources;
  const byRes = new Map(resources.map((r) => [r.id, r]));

  const setCal = (patch: Partial<CalendarPlan>) =>
    onChange({ ...investment, calendar: { stages, resources, ...patch } });
  const setStages = (s: Stage[]) => setCal({ stages: s });
  const setResources = (r: Resource[]) => setCal({ resources: r });

  const sched = resolveSchedule(stages);
  const budget = computeBudget(stages, resources, n);
  const horizon = Math.max(1, n, ...[...sched.values()].map((s) => s.finish));
  const maxMonthly = Math.max(1, ...budget.monthly);

  const addStage = () =>
    setStages([...stages, { id: uid("st"), name: "Этап", kind: "expense", start_month: 0, duration_months: 1, cost: "0" }]);
  const updStage = (i: number, patch: Partial<Stage>) =>
    setStages(stages.map((s, k) => (k === i ? { ...s, ...patch } : s)));
  const rmStage = (i: number) => setStages(stages.filter((_, k) => k !== i));

  const addResource = () =>
    setResources([...resources, { id: uid("r"), name: "Ресурс", unit_price: "0", payment_delay_months: 0 }]);
  const updResource = (i: number, patch: Partial<Resource>) =>
    setResources(resources.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const rmResource = (i: number) => setResources(resources.filter((_, k) => k !== i));

  const stageOptions = (exceptId: string): [string, string][] =>
    [["", "—"], ...stages.filter((s) => s.id !== exceptId).map((s) => [s.id, s.name || s.id] as [string, string])];

  return (
    <div>
      <div className="tab-head">
        <div style={{ minWidth: 0 }}>
          <div className="tab-head__title">Календарный план</div>
          <div className="tab-head__sub">
            Этапы подготовки со сроками, связями и стоимостью → смета и график инвестиций.
          </div>
        </div>
        <Button onClick={addStage}>＋&nbsp;&nbsp;Этап</Button>
      </div>

      {stages.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">Нет этапов</div>
          <div className="tab-empty__sub">
            Опишите подготовку проекта этапами: стройка, закупка/монтаж оборудования, запуск
            производства. Стоимость и сроки сложатся в смету и график инвестиций.
          </div>
          <Button onClick={addStage}>＋&nbsp;&nbsp;Добавить первый этап</Button>
        </div>
      ) : (
        <>
          <div className="sum-row">
            <div className="sum-card">
              <div className="sum-card__label">Смета проекта</div>
              <div className="sum-card__value">{fmtMoney(budget.total)}</div>
            </div>
            <div className="sum-card">
              <div className="sum-card__label">Этапов</div>
              <div className="sum-card__value">{stages.length}</div>
            </div>
            <div className="sum-card">
              <div className="sum-card__label">Ресурсов</div>
              <div className="sum-card__value">{resources.length}</div>
            </div>
            {budget.actualTotal !== null && (
              <div className="sum-card">
                <div className="sum-card__label">Факт (смета)</div>
                <div className="sum-card__value">{fmtMoney(budget.actualTotal)}</div>
              </div>
            )}
          </div>

          {budget.actualTotal !== null && (
            <div className="gantt-card">
              <div className="gantt-card__title">Смета: план-факт (контроль реализации)</div>
              <div className="budget-pf fe-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Этап</th><th>План</th><th>Факт</th><th>Отклонение</th><th>Сроки, финиш (план→факт)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {budget.rows.map((r) => (
                      <tr key={r.id}>
                        <td className="budget-pf__name">{r.name}</td>
                        <td>{fmtMoney(r.cost)}</td>
                        <td>{r.actualCost !== null ? fmtMoney(r.actualCost) : "—"}</td>
                        <td className={r.costVariance && r.costVariance > 0 ? "budget-pf--over" : "budget-pf--under"}>
                          {r.costVariance !== null ? (r.costVariance > 0 ? "+" : "") + fmtMoney(r.costVariance) : "—"}
                        </td>
                        <td>
                          {r.actualFinish !== null
                            ? `М${r.finish} → М${r.actualFinish}${r.scheduleVariance ? ` (${r.scheduleVariance > 0 ? "+" : ""}${r.scheduleVariance} мес.)` : ""}`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Диаграмма Гантта */}
          <div className="gantt-card">
            <div className="gantt-card__title">Диаграмма Гантта</div>
            <div className="gantt">
              {stages.map((s) => {
                const sc = sched.get(s.id);
                if (!sc) return null;
                const kind = (s.kind ?? "expense") as StageKind;
                const left = (sc.start / horizon) * 100;
                const width = (Math.max(1, sc.finish - sc.start) / horizon) * 100;
                const isGroup = stages.some((x) => x.parent_id === s.id);
                return (
                  <div className="gantt-row" key={s.id}>
                    <div className="gantt-label" style={{ paddingLeft: s.parent_id ? 14 : 0 }}>
                      {s.name || s.id}
                    </div>
                    <div className="gantt-track">
                      <div
                        className={"gantt-bar" + (isGroup ? " gantt-bar--group" : "")}
                        style={{ left: `${left}%`, width: `${width}%`, background: KIND[kind].color }}
                        title={`${KIND[kind].label} · мес. ${sc.start}–${sc.finish}`}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="gantt-axis">
              <span>мес. 0</span>
              <span>{horizon}</span>
            </div>
          </div>

          {/* График инвестиций (помесячно) */}
          <div className="gantt-card">
            <div className="gantt-card__title">График инвестиций (начисление по месяцам)</div>
            <div className="inv-bars">
              {budget.monthly.map((v, t) => (
                <div key={t} className="inv-bar-col" title={`мес. ${t}: ${fmtMoney(v)}`}>
                  <div className="inv-bar" style={{ height: `${(v / maxMonthly) * 100}%` }} />
                </div>
              ))}
            </div>
          </div>

          {/* Карточки этапов */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {stages.map((s, i) => {
              const kind = (s.kind ?? "expense") as StageKind;
              const hasRes = !!s.resources && s.resources.length > 0;
              const cost = stageCost(s, byRes);
              const sc = sched.get(s.id);
              return (
                <div className="line-card" key={s.id}>
                  <div className="line-card__head">
                    <span className="stage-dot" style={{ background: KIND[kind].color }} />
                    <div className="line-card__name">
                      <input value={s.name ?? ""} placeholder="Название этапа"
                             onChange={(e) => updStage(i, { name: e.target.value })} />
                    </div>
                    <span className="prop-chip">{KIND[kind].label}</span>
                    {sc && <span className="prop-chip">мес. {sc.start}–{sc.finish}</span>}
                    <button type="button" className="line-card__del" title="Удалить этап" onClick={() => rmStage(i)}>
                      <IconTrash size={16} />
                    </button>
                  </div>

                  <div className="afields-grid">
                    <ESelect label="Тип" value={kind}
                             onChange={(v) => updStage(i, { kind: v as StageKind })} options={KIND_OPTIONS} />
                    <EField label={s.predecessor_id ? "Лаг от предшественника" : "Месяц начала"} prefix="М"
                            value={s.start_month ?? 0}
                            onChange={(v) => updStage(i, { start_month: parseInt(v || "0", 10) || 0 })} />
                    <EField label="Длительность" suffix="мес."
                            value={s.duration_months ?? 1}
                            onChange={(v) => updStage(i, { duration_months: Math.max(1, parseInt(v || "1", 10) || 1) })} />
                    {!hasRes && (
                      <EField label="Стоимость" prefix="₽" value={s.cost ?? "0"}
                              onChange={(v) => updStage(i, { cost: v })} />
                    )}
                    {hasRes && (
                      <div className="efield">
                        <label className="efield__label">Стоимость (из ресурсов)</label>
                        <div className="efield__ro">{fmtMoney(cost)}</div>
                      </div>
                    )}
                    <ESelect label="Предшественник" value={s.predecessor_id ?? ""}
                             onChange={(v) => updStage(i, { predecessor_id: v || null })}
                             options={stageOptions(s.id)} />
                    <ESelect label="Входит в группу" value={s.parent_id ?? ""}
                             onChange={(v) => updStage(i, { parent_id: v || null })}
                             options={stageOptions(s.id)} />
                    {kind === "expense" && (
                      <>
                        <ESelect label="Тайминг стоимости" value={s.cost_timing ?? "uniform"}
                                 onChange={(v) => updStage(i, { cost_timing: v as "uniform" | "on_finish" })}
                                 options={[["uniform", "Равномерно"], ["on_finish", "В конце"]]} />
                        <EField label="Списание (РБП)" suffix="мес."
                                note={(s.amortize_months ?? 0) > 0 ? "Капитализация и списание" : "0 — издержка сразу"}
                                value={s.amortize_months ?? 0}
                                onChange={(v) => updStage(i, { amortize_months: parseInt(v || "0", 10) || 0 })} />
                      </>
                    )}
                    {kind === "asset" && (
                      <>
                        <EField label="Срок службы" suffix="мес." value={s.asset_life_months ?? 12}
                                onChange={(v) => updStage(i, { asset_life_months: Math.max(1, parseInt(v || "1", 10) || 1) })} />
                        <ESelect label="Группа ОС" value={s.asset_category ?? "equipment"}
                                 onChange={(v) => updStage(i, { asset_category: v as "equipment" | "buildings" | "land" | "intangible" })}
                                 options={[["equipment", "Оборудование"], ["buildings", "Здания"], ["land", "Земля"], ["intangible", "НМА"]]} />
                      </>
                    )}
                    {kind === "production" && (
                      <ESelect label="Продукт (старт)" value={s.product_id ?? ""}
                               onChange={(v) => updStage(i, { product_id: v || null })}
                               options={[["", "—"], ...products.map((p) => [p.id, p.name || p.id] as [string, string])]} />
                    )}
                  </div>

                  {resources.length > 0 && kind !== "production" && (
                    <StageResources stage={s} resources={resources}
                                    onChange={(rs) => updStage(i, { resources: rs })} />
                  )}

                  {!stages.some((x) => x.parent_id === s.id) && (
                    <div className="expand-block">
                      <div className="expand-block__head"><span>✓</span>Факт (актуализация)</div>
                      <div className="afields-grid">
                        <EField label="Факт: месяц начала" prefix="М"
                                value={s.actual_start_month ?? ""}
                                onChange={(v) => updStage(i, { actual_start_month: v === "" ? null : parseInt(v, 10) || 0 })} />
                        <EField label="Факт: месяц финиша" prefix="М"
                                value={s.actual_finish_month ?? ""}
                                onChange={(v) => updStage(i, { actual_finish_month: v === "" ? null : parseInt(v, 10) || 0 })} />
                        <EField label="Факт: стоимость" prefix="₽"
                                value={s.actual_cost ?? ""}
                                onChange={(v) => updStage(i, { actual_cost: v === "" ? null : v })} />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            <button type="button" className="add-row" onClick={addStage}>＋&nbsp;&nbsp;Добавить этап</button>
          </div>

          {/* Библиотека ресурсов */}
          <div className="res-lib">
            <div className="res-lib__head">
              <div className="res-lib__title">Ресурсы</div>
              <Button variant="ghost" onClick={addResource}>＋&nbsp;&nbsp;Ресурс</Button>
            </div>
            {resources.length === 0 ? (
              <p className="muted" style={{ fontSize: 12.5, margin: 0 }}>
                Ресурсы (материалы, оборудование, услуги) с ценой и сроком оплаты. Стоимость этапа
                можно считать как Σ(количество×цена).
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {resources.map((r, i) => (
                  <div className="res-row" key={r.id}>
                    <input className="res-row__name" value={r.name ?? ""} placeholder="Ресурс"
                           onChange={(e) => updResource(i, { name: e.target.value })} />
                    <EField label="Цена ед." prefix="₽" value={r.unit_price ?? "0"}
                            onChange={(v) => updResource(i, { unit_price: v })} />
                    <EField label="Отсрочка" suffix="мес." value={r.payment_delay_months ?? 0}
                            onChange={(v) => updResource(i, { payment_delay_months: parseInt(v || "0", 10) || 0 })} />
                    <button type="button" className="line-card__del" title="Удалить ресурс" onClick={() => rmResource(i)}>
                      <IconTrash size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/** Назначение ресурсов этапу: строки (ресурс × количество). */
function StageResources({ stage, resources, onChange }: {
  stage: Stage;
  resources: Resource[];
  onChange: (rs: Stage["resources"]) => void;
}) {
  const rows = stage.resources ?? [];
  const opts: [string, string][] = [["", "—"], ...resources.map((r) => [r.id, r.name || r.id] as [string, string])];
  const add = () => onChange([...rows, { resource_id: resources[0]?.id ?? "", quantity: "0" }]);
  const upd = (i: number, patch: Partial<{ resource_id: string; quantity: string }>) =>
    onChange(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const rm = (i: number) => onChange(rows.filter((_, k) => k !== i));
  return (
    <div className="expand-block">
      <div className="expand-block__head"><span>▣</span>Ресурсы этапа</div>
      {rows.map((row, i) => (
        <div className="res-assign" key={i}>
          <ESelect label="Ресурс" value={row.resource_id}
                   onChange={(v) => upd(i, { resource_id: v })} options={opts} />
          <EField label="Количество" value={row.quantity ?? "0"} onChange={(v) => upd(i, { quantity: v })} />
          <button type="button" className="line-card__del" onClick={() => rm(i)}><IconTrash size={15} /></button>
        </div>
      ))}
      <button type="button" className="add-row add-row--sm" onClick={add}>＋&nbsp;&nbsp;Ресурс этапа</button>
    </div>
  );
}
