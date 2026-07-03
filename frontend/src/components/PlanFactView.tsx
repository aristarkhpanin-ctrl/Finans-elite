import { line, type CalcResponse } from "../api/calc";
import { fmtMillions, fmtTable } from "../format";
import { GRANDS, SUBTOTALS } from "./StatementTable";

const num = (v: string | undefined): number => {
  const x = Number(v ?? 0);
  return Number.isFinite(x) ? x : 0;
};

const NBSP = " ";
const fmtInt = (v: number): string => {
  const r = Math.round(v);
  const s = String(Math.abs(r)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return (r < 0 ? "−" : "") + s;
};

/**
 * Вкладка «План-факт» (макет «Этап 16»): две таблицы по фактическим периодам —
 * факт (план серым над фактом) и отклонение (факт − план) со стрелками и цветом
 * «лучше/хуже». Знак денежного потока уже несёт смысл, поэтому положительное
 * отклонение = больше денег = лучше (зелёное), отрицательное = хуже (красное).
 */
export function PlanFactView({ result, factUntil }: { result: CalcResponse; factUntil: number }) {
  const fact = result.actualized_cashflow;
  const variance = result.cashflow_variance;
  if (!fact) return null;

  const factN = Math.min(Math.max(factUntil + 1, 0), result.n);
  const months = Array.from({ length: factN }, (_, i) => i);
  const plan = result.cashflow;

  const kindOf = (code: string) =>
    GRANDS.cashflow.has(code) ? "grand" : SUBTOTALS.cashflow.has(code) ? "sub" : "";

  // Статы: Σ отклонение потока (по C29) и Исполнение по выручке (C1 факт/план).
  const flowVar = variance
    ? months.reduce((s, i) => s + num(line(variance, "C29")[i]), 0)
    : months.reduce((s, i) => s + (num(line(fact, "C29")[i]) - num(line(plan, "C29")[i])), 0);
  const planReceipts = months.reduce((s, i) => s + num(line(plan, "C1")[i]), 0);
  const factReceipts = months.reduce((s, i) => s + num(line(fact, "C1")[i]), 0);
  const execPct = planReceipts !== 0 ? Math.round((factReceipts / planReceipts) * 100) : null;

  const rangeLabel = factN > 0 ? `М1–М${factN}` : "—";

  return (
    <div>
      <div className="pf-head">
        <div style={{ minWidth: 0 }}>
          <div className="report-head__title">План-факт · движение денежных средств</div>
          <div className="report-head__sub">
            Факт введён за {rangeLabel} · сравнивается с планом по фактическим периодам
          </div>
        </div>
        <div className="pf-stat">
          <div className="pf-stat__item">
            <span className="pf-stat__label">Σ отклонение потока</span>
            <span className={"pf-stat__val" + (flowVar > 0 ? " pf-stat__val--good" : flowVar < 0 ? " pf-stat__val--bad" : "")}>
              {flowVar > 0 ? "+" : ""}
              {fmtInt(flowVar)} ₽
            </span>
          </div>
          <div className="pf-stat__div" />
          <div className="pf-stat__item">
            <span className="pf-stat__label">Исполнение по выручке</span>
            <span className="pf-stat__val">{execPct !== null ? `${execPct}%` : "—"}</span>
          </div>
        </div>
      </div>

      {/* Таблица 1: факт (план серым над фактом) */}
      <div className="tbl-caption">
        <span className="tbl-caption__num">1</span>
        <span className="tbl-caption__strong">Факт за прошедшие периоды</span>
        <span className="tbl-caption__hint">план — серым над фактом · ₽</span>
      </div>
      <div className="fin2-wrap fe-scroll">
        <div className="fin2">
          <div className="fin2-row">
            <div className="fin2-corner">
              <span className="fin2-code">код</span>Статья
            </div>
            {months.map((i) => (
              <div key={i} className="fin2-month">
                М{i + 1}
              </div>
            ))}
            <div className="fin2-total-head">Итого</div>
          </div>
          {plan.lines.map((l) => {
            const kind = kindOf(l.code);
            const factVals = line(fact, l.code);
            const planVals = line(plan, l.code);
            const totFact = months.reduce((s, i) => s + num(factVals[i]), 0);
            const totPlan = months.reduce((s, i) => s + num(planVals[i]), 0);
            return (
              <div key={l.code} className={"fin2-row" + (kind ? ` fin2-row--${kind}` : "")}>
                <div className="fin2-label" title={l.label}>
                  <span className="fin2-code">{l.code}</span>
                  <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {l.label}
                  </span>
                </div>
                {months.map((i) => (
                  <div key={i} className="fin2-cell pf-cell">
                    <span className="pf-cell__plan">{fmtTable(planVals[i]).text}</span>
                    <span className="pf-cell__fact">{fmtTable(factVals[i]).text}</span>
                  </div>
                ))}
                <div className="pf-total">
                  <span className="pf-total__plan">{fmtInt(totPlan)}</span>
                  <span className="pf-total__fact">{fmtInt(totFact)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Таблица 2: отклонение (факт − план) */}
      <div className="tbl-caption tbl-caption--2">
        <span className="tbl-caption__num">2</span>
        <span className="tbl-caption__strong">Отклонение (факт − план)</span>
        <span className="tbl-caption__hint">зелёный — лучше плана, красный — хуже</span>
      </div>
      <div className="fin2-wrap fe-scroll">
        <div className="fin2">
          <div className="fin2-row">
            <div className="fin2-corner">
              <span className="fin2-code">код</span>Статья
            </div>
            {months.map((i) => (
              <div key={i} className="fin2-month">
                М{i + 1}
              </div>
            ))}
            <div className="fin2-total-head">Σ&nbsp;откл.</div>
          </div>
          {plan.lines.map((l) => {
            const kind = kindOf(l.code);
            const devVals = months.map((i) =>
              variance ? num(line(variance, l.code)[i]) : num(line(fact, l.code)[i]) - num(line(plan, l.code)[i]),
            );
            const devTot = devVals.reduce((s, v) => s + v, 0);
            const devClass = (v: number) => (v > 0 ? " dev-cell--good" : v < 0 ? " dev-cell--bad" : "");
            return (
              <div key={l.code} className={"fin2-row" + (kind ? ` fin2-row--${kind}` : "")}>
                <div className="fin2-label" title={l.label}>
                  <span className="fin2-code">{l.code}</span>
                  <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {l.label}
                  </span>
                </div>
                {devVals.map((v, i) => (
                  <div key={i} className={"fin2-cell dev-cell" + devClass(v)}>
                    {v !== 0 && <span className="dev-arrow">{v > 0 ? "▲" : "▼"}</span>}
                    {v === 0 ? "—" : fmtInt(Math.abs(v))}
                  </div>
                ))}
                <div className={"pf-total dev-cell" + devClass(devTot)} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                  {devTot !== 0 && <span className="dev-arrow">{devTot > 0 ? "▲" : "▼"}</span>}
                  {devTot === 0 ? "—" : fmtInt(Math.abs(devTot))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="pf-legend">
        <span className="pf-legend__item">
          <span className="pf-legend__sw" style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }} />
          план
        </span>
        <span className="pf-legend__item">
          <span className="pf-legend__sw" style={{ background: "var(--good)" }} />
          лучше плана
        </span>
        <span className="pf-legend__item">
          <span className="pf-legend__sw" style={{ background: "var(--danger)" }} />
          хуже плана
        </span>
        <span className="pf-legend__hint">
          Будущие месяцы (после М{factN}) сравнению не подлежат — только план ·{" "}
          {fmtMillions(String(factReceipts), { digits: 1 })} факт. выручки
        </span>
      </div>
    </div>
  );
}
