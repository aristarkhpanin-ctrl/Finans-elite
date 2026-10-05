import type { CalcResponse } from "../api/calc";
import { aggregateFlowSeries, aggregateStatement, defaultPeriod, periodLabels, type Period } from "../aggregate";
import { fmtMillions, percent } from "../format";
import type { MetricCard, ValueCard } from "../metricCards";
import { DebtServiceView } from "./DebtServiceView";
import { HintBadge } from "./EditorField";
import { fmtInt } from "./monthlyGrid.logic";
import { GRANDS, StatementTable, SUBTOTALS } from "./StatementTable";
import { ScrollRegion } from "./ui";

/*
 * Блоки экрана результатов — **одна разметка на два экрана**: результаты проекта у
 * владельца и план по ссылке у инвестора или банка (пакет L, L4). Копия разметки на
 * второй странице разошлась бы с первой при первой же правке — так уже было с
 * карточкой ошибки, жившей на шести страницах (пакет I).
 */

export const STATEMENTS = [
  ["income", "Прибыли и убытки"],
  ["cashflow", "Кэш-фло"],
  ["balance", "Баланс"],
  ["profit_use", "Использование прибыли"],
] as const;

export type StatementKey = (typeof STATEMENTS)[number][0];

export const RESULT_TAB_LABELS: Record<string, string> = {
  summary: "Сводка",
  income: "Прибыли и убытки",
  cashflow: "Кэш-фло",
  balance: "Баланс",
  ratios: "Коэффициенты",
  charts: "Графики",
  tables: "Таблицы",
  plan_fact: "План-факт",
};

export function isStatementTab(tab: string): tab is StatementKey {
  return STATEMENTS.some(([k]) => k === tab);
}

/** Сетка карточек показателей; ``compact`` — карточки оценки (мельче, без вердикта). */
export function MetricCards({ cards, compact = false }: {
  cards: (MetricCard | ValueCard)[];
  compact?: boolean;
}) {
  return (
    <div className={"metric-grid" + (compact ? " metric-grid--val" : "")}>
      {cards.map((c) => {
        const tone = "tone" in c && c.tone ? ` metric-card2__value--${c.tone}` : "";
        return (
          <div key={c.label} className="metric-card2">
            <div className="metric-card2__top">
              <span className="metric-card2__label" style={compact ? { fontSize: 11.5 } : undefined}>
                {c.label}
              </span>
              <HintBadge text={c.hint} />
            </div>
            <div className={"metric-card2__value" + tone} style={compact ? { fontSize: 17 } : undefined}>
              {c.value}
            </div>
            {"sub" in c && <div className="metric-card2__sub">{c.sub}</div>}
          </div>
        );
      })}
    </div>
  );
}

/** Вкладки результатов. Отчёты — одна вкладка с переключателем внутри панели отчёта. */
export function ResultTabs({ tabs, active, onSelect }: {
  tabs: string[];
  active: string;
  onSelect: (tab: string) => void;
}) {
  return (
    <div className="etabs-wrap" style={{ margin: "20px 0", borderTop: "1px solid var(--border)", background: "none", padding: 0 }}>
      <div className="etabs fe-scroll">
        {tabs.map((key) => (
          <button
            aria-pressed={active === key}
            key={key}
            type="button"
            className={"etab" + (active === key ? " etab--active" : "")}
            onClick={() => onSelect(key)}
          >
            {RESULT_TAB_LABELS[key]}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Отчёт с переключателями периода и отчёта; детализация строк сворачивается суммами. */
export function StatementPanel({ data, which, period, onPeriod, onWhich }: {
  data: CalcResponse;
  which: StatementKey;
  period: Period | null;
  onPeriod: (p: Period) => void;
  onWhich: (k: StatementKey) => void;
}) {
  const eff = period ?? defaultPeriod(data.n);
  const labels = periodLabels(data.n, eff);
  const agg = aggregateStatement(data[which], which === "balance" ? "balance" : "flow", data.n, eff);
  // Детализация строк (drill-down): слагаемые — потоки, сворачиваются суммами.
  const prefix = which === "income" ? "I" : which === "cashflow" ? "C" : null;
  const details = new Map(
    (data.details ?? [])
      .filter((d) => prefix !== null && d.code.startsWith(prefix))
      .map((d) => [
        d.code,
        d.items.map((i) => ({ name: i.name, values: aggregateFlowSeries(i.values, data.n, eff) })),
      ]),
  );
  const title = RESULT_TAB_LABELS[which];
  const sub =
    eff === "month"
      ? `Помесячно · ${data.n} мес · суммы в ₽`
      : eff === "quarter"
        ? `По кварталам · ${labels.length} кв (${data.n} мес) · суммы в ₽`
        : `По годам проекта · ${labels.length} г. (${data.n} мес) · суммы в ₽`;
  return (
    <>
      <div className="report-head">
        <div style={{ minWidth: 0 }}>
          <div className="report-head__title">{title}</div>
          <div className="report-head__sub">{sub}</div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <div className="report-switch" aria-label="Период отображения">
            {(["month", "quarter", "year"] as const).map((p) => (
              <button aria-pressed={eff === p} key={p} type="button" className={eff === p ? "on" : ""} onClick={() => onPeriod(p)}>
                {p === "month" ? "Месяц" : p === "quarter" ? "Квартал" : "Год"}
              </button>
            ))}
          </div>
          <div className="report-switch">
            {STATEMENTS.map(([k, label]) => (
              <button aria-pressed={which === k} key={k} type="button" className={which === k ? "on" : ""} onClick={() => onWhich(k)}>
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <StatementTable title={title} statement={agg} n={labels.length} subtotals={SUBTOTALS[which]}
                      grands={GRANDS[which]} labels={labels} details={details} />
    </>
  );
}

/** Замечания расчёта под сводкой. */
export function CalcWarnings({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="warn-block">
      <div className="warn-block__head">
        <span style={{ color: "var(--warn)" }}>⚠</span>Замечания по расчёту
      </div>
      {warnings.map((w, i) => (
        <div key={i} className="warn-block__row">
          <span className="warn-banner__dot" />
          <span className="warn-block__text">{w}</span>
          <span className="level-chip level-chip--warn">предупр.</span>
        </div>
      ))}
    </div>
  );
}

/**
 * Таблицы под карточками сводки: маржа продуктов и подразделений, абонентская база,
 * доходы участников и покрытие долга. Каждая — только где есть что показать.
 */
export function SummaryExtras({ data }: { data: CalcResponse }) {
  return (
    <>
      {data.product_margins.products.length > 0 && (
        <>
          <h2 className="rsection-label">Маржа по продуктам (рецептура)</h2>
          <ScrollRegion className="contrib-wrap" label="Маржа по продуктам">
            <div className="contrib-row contrib-row--head">
              <div className="contrib-label">Продукт</div>
              <div className="contrib-cell">Выручка</div>
              <div className="contrib-cell">Материалы</div>
              <div className="contrib-cell">Сдельная ЗП</div>
              <div className="contrib-cell">Маржа</div>
              <div className="contrib-cell">Маржа, %</div>
            </div>
            {data.product_margins.products.map((p) => {
              const neg = Number(p.margin) < 0;
              return (
                <div className="contrib-row" key={p.product_id}>
                  <div className="contrib-label">{p.name || p.product_id}</div>
                  <div className="contrib-cell">{fmtMillions(p.revenue, { digits: 2 })}</div>
                  <div className="contrib-cell">{fmtMillions(p.bom_cost, { digits: 2 })}</div>
                  <div className="contrib-cell">{fmtMillions(p.piece_wages, { digits: 2 })}</div>
                  <div className={"contrib-cell" + (neg ? " contrib-cell--neg" : "")}>
                    {fmtMillions(p.margin, { sign: true, digits: 2 })}
                  </div>
                  <div className={"contrib-cell" + (neg ? " contrib-cell--neg" : "")}>
                    {p.margin_share != null ? percent(p.margin_share, 1) : "—"}
                  </div>
                </div>
              );
            })}
          </ScrollRegion>
          {Number(data.product_margins.unallocated_direct) > 0 && (
            <div className="field-note" style={{ marginTop: 8 }}>
              Суммовые прямые издержки {fmtMillions(data.product_margins.unallocated_direct, { digits: 2 })} не
              распределяются по продуктам (заданы без рецептуры).
            </div>
          )}
        </>
      )}

      {(data.division_margins ?? []).length > 0 && (
        <>
          <h2 className="rsection-label">Доходы подразделений</h2>
          <ScrollRegion className="contrib-wrap" label="Доходы подразделений">
            <div className="contrib-row contrib-row--head">
              <div className="contrib-label">Подразделение</div>
              <div className="contrib-cell">Выручка</div>
              <div className="contrib-cell">Материалы</div>
              <div className="contrib-cell">Сдельная ЗП</div>
              <div className="contrib-cell">Маржа</div>
              <div className="contrib-cell">Маржа, %</div>
            </div>
            {data.division_margins.map((d) => {
              const neg = Number(d.margin) < 0;
              return (
                <div className="contrib-row" key={d.division_id}>
                  <div className="contrib-label">
                    {d.name || d.division_id}
                    <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>· {d.product_count} прод.</span>
                  </div>
                  <div className="contrib-cell">{fmtMillions(d.revenue, { digits: 2 })}</div>
                  <div className="contrib-cell">{fmtMillions(d.bom_cost, { digits: 2 })}</div>
                  <div className="contrib-cell">{fmtMillions(d.piece_wages, { digits: 2 })}</div>
                  <div className={"contrib-cell" + (neg ? " contrib-cell--neg" : "")}>
                    {fmtMillions(d.margin, { sign: true, digits: 2 })}
                  </div>
                  <div className={"contrib-cell" + (neg ? " contrib-cell--neg" : "")}>
                    {d.margin_share != null ? percent(d.margin_share, 1) : "—"}
                  </div>
                </div>
              );
            })}
          </ScrollRegion>
          <div className="field-note" style={{ marginTop: 8 }}>
            Свёртка маржи продуктов по бизнес-единицам; продукты без рецептуры/подразделения в свёртку не входят.
          </div>
        </>
      )}

      {(data.subscription_base ?? []).length > 0 && (
        <>
          <h2 className="rsection-label">Абонентская база</h2>
          <ScrollRegion className="contrib-wrap" label="Абонентская база">
            <div className="contrib-row contrib-row--head">
              <div className="contrib-label">Продукт</div>
              <div className="contrib-cell">На старте</div>
              <div className="contrib-cell">Пришло всего</div>
              <div className="contrib-cell">Ушло всего</div>
              <div className="contrib-cell">База на конец</div>
            </div>
            {data.subscription_base.map((s) => {
              const sum = (xs: (string | number)[]) =>
                xs.reduce((a: number, c) => a + Number(c), 0);
              const last = Number(s.base[s.base.length - 1] ?? 0);
              const opening = Number(s.base[0] ?? 0) + Number(s.churned[0] ?? 0)
                - Number(s.new[0] ?? 0);
              return (
                <div className="contrib-row" key={s.product_id}>
                  <div className="contrib-label">{s.name || s.product_id}</div>
                  <div className="contrib-cell">{fmtInt(opening)}</div>
                  <div className="contrib-cell">{fmtInt(sum(s.new))}</div>
                  <div className="contrib-cell contrib-cell--neg">−{fmtInt(sum(s.churned))}</div>
                  <div className="contrib-cell">{fmtInt(last)}</div>
                </div>
              );
            })}
          </ScrollRegion>
          <div className="field-note" style={{ marginTop: 8 }}>
            База на конец месяца и есть объём продаж подписки. «Ушло» — выбытие по
            заданному оттоку; при нулевом оттоке эта колонка пуста не потому, что никто
            не уходит, а потому, что отток не задан.
          </div>
        </>
      )}

      {(data.participants ?? []).length > 0 && (
        <>
          <h2 className="rsection-label">Доходы участников финансирования</h2>
          <ScrollRegion className="contrib-wrap" label="Доходы участников финансирования">
            <div className="contrib-row contrib-row--head">
              <div className="contrib-label">Участник</div>
              <div className="contrib-cell">Вложено</div>
              <div className="contrib-cell">Получено</div>
              <div className="contrib-cell">NPV</div>
              <div className="contrib-cell">IRR</div>
              <div className="contrib-cell">IRR с уч. остатка</div>
            </div>
            {data.participants.map((p) => {
              const neg = Number(p.npv_with_terminal ?? p.npv) < 0;
              return (
                <div className="contrib-row" key={p.id}>
                  <div className="contrib-label">
                    {p.name}
                    {p.kind === "lender" && <span className="fin2-code" style={{ marginLeft: 6 }}>заём</span>}
                  </div>
                  <div className="contrib-cell">{fmtMillions(p.invested, { digits: 2 })}</div>
                  <div className="contrib-cell">{fmtMillions(p.withdrawn, { digits: 2 })}</div>
                  <div className={"contrib-cell" + (neg ? " contrib-cell--neg" : "")}>
                    {fmtMillions(p.npv_with_terminal ?? p.npv, { sign: true, digits: 2 })}
                  </div>
                  <div className="contrib-cell">
                    {p.irr_annual != null ? percent(p.irr_annual, 1) : "—"}
                  </div>
                  <div className="contrib-cell">
                    {p.irr_with_terminal_annual != null ? percent(p.irr_with_terminal_annual, 1) : "—"}
                  </div>
                </div>
              );
            })}
          </ScrollRegion>
          <div className="field-note" style={{ marginTop: 8 }}>
            NPV и «IRR с уч. остатка» — с условным возвратом на конец горизонта: акционерам —
            собственного капитала (B33), кредиторам — непогашенного тела займа.
          </div>
        </>
      )}

      <DebtServiceView debt={data.debt_service} />
    </>
  );
}
