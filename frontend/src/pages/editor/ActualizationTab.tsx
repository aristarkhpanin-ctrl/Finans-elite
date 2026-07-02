import { useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import type { Actualization } from "../../api/model";
import type { CalcResponse } from "../../api/calc";
import { ESelect } from "../../components/EditorField";
import { IconChart } from "../../components/icons";
import { Button, Switch } from "../../components/ui";

interface Props {
  n: number;
  actualization: Actualization;
  onChange: (a: Actualization) => void;
}

/** Строки Кэш-фло для ввода факта: [код, подпись, приток?]. */
const LINES: Array<[string, string, boolean]> = [
  ["C1", "Поступления от продаж", true],
  ["C2", "Затраты на материалы", false],
  ["C5", "Общие издержки", false],
  ["C6", "Затраты на персонал", false],
  ["C12", "Налоги", false],
  ["C14", "Приобретение активов", false],
];

const num = (v: string | undefined): number | null => {
  if (v === undefined || v === "") return null;
  const x = Number(String(v).replace(",", "."));
  return Number.isFinite(x) ? x : null;
};

const NBSP = " ";
const fmtInt = (v: number): string => {
  const r = Math.round(v);
  const s = String(Math.abs(r)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return (r < 0 ? "−" : "") + s;
};

/** Вкладка «Факт» (макет «Этап 11»): актуализация Кэш-фло план/факт. */
export function ActualizationTab({ n, actualization, onChange }: Props) {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const calc = qc.getQueryData<CalcResponse>(["calc", id]);

  const enabled = actualization.actual_until >= 0;
  const until = Math.min(Math.max(actualization.actual_until, 0), n - 1);
  const actuals = actualization.actuals ?? {};

  const planOf = (code: string): string[] | null => {
    const ln = calc?.cashflow.lines.find((l) => l.code === code);
    return ln ? ln.values : null;
  };

  const setActual = (code: string, month: number, val: string) => {
    const cur = actuals[code] ?? [];
    const next = Array.from({ length: n }, (_, k) => (k === month ? val : cur[k] ?? ""));
    onChange({ ...actualization, actuals: { ...actuals, [code]: next } });
  };

  // Прогресс заполнения: статьи × месяцы факта
  const totalCells = LINES.length * (until + 1);
  const filledCells = LINES.reduce((s, [code]) => {
    const vals = actuals[code] ?? [];
    let c = 0;
    for (let t = 0; t <= until; t++) if (vals[t] !== undefined && vals[t] !== "") c++;
    return s + c;
  }, 0);
  const pct = totalCells ? Math.round((filledCells / totalCells) * 100) : 0;

  return (
    <div className="editor-col" style={{ maxWidth: "none" }}>
      <div className="esec">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, flexWrap: "wrap" }}>
          <Switch
            label="Включить актуализацию (план-факт)"
            checked={enabled}
            onChange={(on) => onChange({ ...actualization, actual_until: on ? 0 : -1 })}
          />
          {enabled && (
            <Link to={`/projects/${id}/results`} className="link-btn" style={{ fontSize: 13 }}>
              → Результаты · План-факт
            </Link>
          )}
        </div>
        {!enabled && (
          <div className="tab-empty" style={{ marginTop: 16, padding: "38px 24px" }}>
            <div className="tab-empty__ico">
              <IconChart size={26} />
            </div>
            <div className="tab-empty__title">Факт не учитывается</div>
            <div className="tab-empty__sub">
              Включите актуализацию — фактические значения Кэш-фло заменят план за прошедшие
              месяцы, а в результатах появится сравнение план/факт.
            </div>
            <Button onClick={() => onChange({ ...actualization, actual_until: 0 })}>
              Включить актуализацию
            </Button>
          </div>
        )}
      </div>

      {enabled && (
        <div className="esec">
          <div className="esec__head">
            <div className="esec__num">1</div>
            <div style={{ minWidth: 0 }}>
              <div className="esec__title">Фактические данные</div>
              <div className="esec__desc">
                План серым — из последнего расчёта; отклонение считается по знаку статьи.
              </div>
            </div>
          </div>

          <div className="esec__grid" style={{ marginBottom: 14 }}>
            <ESelect
              label="Факт до месяца"
              hint="Включительно: до этого месяца план заменяется фактом"
              value={String(until)}
              onChange={(v) => onChange({ ...actualization, actual_until: parseInt(v, 10) })}
              options={Array.from({ length: n }, (_, i) => [String(i), `М${i + 1}`] as [string, string])}
            />
            <div className="efield" style={{ gridColumn: "span 2" }}>
              <div className="efield__labelrow">
                <span className="efield__label">Заполнение факта</span>
              </div>
              <div className="fact-progress" style={{ height: 42 }}>
                <div className="fact-progress__track">
                  <div className="fact-progress__bar" style={{ width: `${pct}%` }} />
                </div>
                <span className="fact-progress__text">
                  {pct}% · {filledCells} из {totalCells} ячеек · {LINES.length} статей × {until + 1} мес.
                </span>
              </div>
            </div>
          </div>

          {!calc && (
            <p className="muted" style={{ fontSize: 12.5, marginTop: 0 }}>
              План появится после первого расчёта («Рассчитать →»).
            </p>
          )}

          <div className="mgrid-wrap fe-scroll">
            <div className="mgrid-inner">
              <div className="mgrid-row">
                <div className="mgrid-corner">Статья{NBSP}→</div>
                {Array.from({ length: n }, (_, i) => (
                  <div key={i} className="mgrid-month" style={i > until ? { opacity: 0.45 } : undefined}>
                    М{i + 1}
                  </div>
                ))}
                <div className="fact-total" style={{ background: "var(--surface-2)", font: "600 10.5px var(--font-ui)", letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--subtle)" }}>
                  Σ откл.
                </div>
              </div>

              {LINES.map(([code, label, inflow]) => {
                const plan = planOf(code);
                const vals = actuals[code] ?? [];
                let devSum = 0;
                let hasDev = false;

                const cells = Array.from({ length: n }, (_, t) => {
                  const off = t > until;
                  const fact = num(vals[t]);
                  const planV = plan ? num(plan[t]) : null;
                  const dev = !off && fact !== null && planV !== null ? fact - planV : null;
                  if (dev !== null) {
                    devSum += dev;
                    hasDev = true;
                  }
                  return (
                    <div key={t} className={"fact-cell" + (off ? " fact-cell--off" : "")}>
                      <span className="fact-cell__plan">{planV !== null ? fmtInt(planV) : "—"}</span>
                      <input
                        className="fact-cell__input"
                        inputMode="decimal"
                        disabled={off}
                        placeholder={off ? "" : "0"}
                        value={vals[t] ?? ""}
                        onChange={(e) => setActual(code, t, e.target.value)}
                        title={`${label} · М${t + 1}`}
                      />
                      <span
                        className={
                          "fact-cell__dev" +
                          (dev === null ? "" : dev >= 0 ? " fact-cell__dev--good" : " fact-cell__dev--bad")
                        }
                      >
                        {dev !== null && dev !== 0 ? (dev > 0 ? "+" : "") + fmtInt(dev) : ""}
                      </span>
                    </div>
                  );
                });

                return (
                  <div key={code} className="mgrid-row">
                    <div className="mgrid-label">
                      <div className="mgrid-title" style={{ display: "flex", alignItems: "center", gap: 7 }}>
                        <span
                          className="dot-label"
                          style={{ background: inflow ? "var(--primary)" : "var(--warn)" }}
                        />
                        {label}
                      </div>
                      <div className="field-note" style={{ fontSize: 10.5 }}>
                        {code} · план, ₽/мес
                      </div>
                    </div>
                    {cells}
                    <div
                      className={
                        "fact-total" +
                        (hasDev ? (devSum >= 0 ? " fact-cell__dev--good" : " fact-cell__dev--bad") : "")
                      }
                    >
                      {hasDev ? (devSum > 0 ? "+" : "") + fmtInt(devSum) : "—"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="fact-legend">
            <span className="fact-legend__item">
              <span style={{ color: "var(--subtle)", fontFamily: "var(--font-mono)", fontSize: 10 }}>123</span>
              план из расчёта
            </span>
            <span className="fact-legend__item">
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>0</span>
              ввод факта
            </span>
            <span className="fact-legend__item">
              <span className="fact-cell__dev--good" style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>+12</span>
              лучше плана
            </span>
            <span className="fact-legend__item">
              <span className="fact-cell__dev--bad" style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>−12</span>
              хуже плана
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
