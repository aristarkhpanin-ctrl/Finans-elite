import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Actualization } from "../../api/model";
import type { CalcResponse } from "../../api/calc";
import {
  downloadCashflowTemplate, FACT_LINES, parseCashflowRows, readCashflowXlsx, type ParsedSheet,
} from "../../cashflowXlsx";
import { ESelect } from "../../components/EditorField";
import { IconChart, IconDownload, IconUpload } from "../../components/icons";
import { useToast } from "../../components/Toast";
import { Button, Switch } from "../../components/ui";
import { CashflowImport } from "./CashflowImport";

interface Props {
  n: number;
  /** Дата старта модели: по ней месяцы выгрузки ДДС ложатся на месяцы горизонта. */
  start: string;
  actualization: Actualization;
  onChange: (a: Actualization) => void;
}

/**
 * Строки для ввода факта: основные — всегда, остальные потоки кэш-фло — когда в них
 * уже есть факт (например, после импорта ДДС), иначе загруженное было бы невидимо.
 */
const BASE = new Set(["C1", "C2", "C5", "C6", "C12", "C14"]);

const num = (v: string | null | undefined): number | null => {
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
export function ActualizationTab({ n, start, actualization, onChange }: Props) {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const calc = qc.getQueryData<CalcResponse>(["calc", id]);
  const fileRef = useRef<HTMLInputElement>(null);
  const [sheet, setSheet] = useState<ParsedSheet | null>(null);

  const enabled = actualization.actual_until >= 0;
  const until = Math.min(Math.max(actualization.actual_until, 0), n - 1);
  const actuals = actualization.actuals ?? {};
  const LINES: Array<[string, string, boolean]> = FACT_LINES
    .filter((l) => BASE.has(l.code) || (actuals[l.code] ?? []).some((v) => v !== null && v !== ""))
    .map((l) => [l.code, l.label, l.inflow]);

  // Факт ДДС из Excel или 1С (L7): файл разбирается на клиенте, сопоставление статей
  // человек видит до загрузки.
  const onImportFile = async (file: File) => {
    try {
      const parsed = parseCashflowRows(await readCashflowXlsx(file), start, n);
      if (parsed.error) {
        toast("Файл не разобран", { kind: "warn", sub: parsed.error });
        return;
      }
      if (parsed.articles.length === 0) {
        toast("В файле нет статей с суммами за месяцы горизонта", { kind: "warn" });
        return;
      }
      setSheet(parsed);
    } catch {
      toast("Не удалось прочитать файл — нужен XLSX", { kind: "error" });
    }
  };

  const planOf = (code: string): string[] | null => {
    const ln = calc?.cashflow.lines.find((l) => l.code === code);
    return ln ? ln.values : null;
  };

  // Пустая ячейка — «факт ещё не внесён» (null): месяц остаётся плановым, а не нулевым.
  const setActual = (code: string, month: number, val: string) => {
    const cur = actuals[code] ?? [];
    const next = Array.from({ length: n }, (_, k) =>
      k === month ? (val.trim() === "" ? null : val) : cur[k] ?? null);
    onChange({ ...actualization, actuals: { ...actuals, [code]: next } });
  };

  // Прогресс заполнения: статьи × месяцы факта
  const totalCells = LINES.length * (until + 1);
  const filledCells = LINES.reduce((s, [code]) => {
    const vals = actuals[code] ?? [];
    let c = 0;
    for (let t = 0; t <= until; t++) if (vals[t] !== undefined && vals[t] !== null && vals[t] !== "") c++;
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

          <div className="fact-import">
            <div className="fact-import__text">
              Факт ДДС из Excel или 1С: статьи по строкам, месяцы по колонкам — выгрузка
              «Анализ движения денежных средств» подходит как есть. Пустая ячейка — факта
              нет, месяц остаётся плановым.
            </div>
            <div className="fact-import__actions">
              <Button variant="ghost" onClick={async () => {
                try {
                  await downloadCashflowTemplate(start, n);
                  toast("Шаблон XLSX скачан", { kind: "success" });
                } catch {
                  toast("Не удалось сформировать шаблон", { kind: "error" });
                }
              }}>
                <IconDownload size={15} />
                <span style={{ marginLeft: 6 }}>Шаблон XLSX</span>
              </Button>
              <Button variant="ghost" onClick={() => fileRef.current?.click()}>
                <IconUpload size={15} />
                <span style={{ marginLeft: 6 }}>Загрузить из Excel или 1С</span>
              </Button>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx"
              aria-label="Файл с фактом ДДС"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void onImportFile(f);
                e.target.value = "";
              }}
            />
          </div>

          <div className="mgrid-wrap fe-scroll">
            <div className="mgrid-inner">
              <div className="mgrid-row">
                <div className="mgrid-corner">Статья{NBSP}→</div>
                {Array.from({ length: n }, (_, i) => (
                  <div key={i} className={"mgrid-month" + (i > until ? " mgrid-month--off" : "")}>
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
                      {/* Без заполнителя «0»: пустая ячейка — не ноль, а «факта нет». */}
                      <input
                        className="fact-cell__input"
                        inputMode="decimal"
                        disabled={off}
                        value={vals[t] ?? ""}
                        onChange={(e) => setActual(code, t, e.target.value)}
                        title={`${label} · М${t + 1}`}
                      />
                      <span
                        className={
                          "fact-cell__dev" +
                          (dev === null ? "" : better(dev, inflow) ? " fact-cell__dev--good" : " fact-cell__dev--bad")
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
                        (hasDev ? (better(devSum, inflow) ? " fact-cell__dev--good" : " fact-cell__dev--bad") : "")
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
              ввод факта; пусто — факта нет, месяц плановый
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
      {sheet && (
        <CashflowImport sheet={sheet} actualization={actualization} n={n}
                        onApply={onChange} onClose={() => setSheet(null)} />
      )}
    </div>
  );
}

/**
 * Лучше ли плана: у поступления — больше, у выплаты — меньше. Раньше любое превышение
 * красилось зелёным, и перерасход по зарплате выглядел удачей (L7).
 */
export function better(dev: number, inflow: boolean): boolean {
  return inflow ? dev >= 0 : dev <= 0;
}
