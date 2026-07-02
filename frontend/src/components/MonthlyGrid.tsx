import { useEffect, useRef, useState } from "react";
import type { ClipboardEvent } from "react";
import { Button, Modal } from "./ui";
import { useToast } from "./Toast";

/**
 * Помесячная сетка редактора (макет «Этап 6», замена MonthlySeries):
 * шапка «Период →» + М1..М{N}, sticky label-колонка с Σ-чипом (или средним)
 * и «↘ заполнить все» (модалка), ячейки-инпуты (mono, фокус-кольцо),
 * вычисляемые readonly-строки, вставка диапазона из Excel от активной ячейки
 * (разделители \t ; \n, десятичная запятая) с подсветкой и тостом.
 */
export interface MonthlyRow {
  key: string;
  title: string;
  /** Редактируемый ряд (строки Decimal). */
  values?: string[];
  onChange?: (values: string[]) => void;
  /** Вычисляемый readonly-ряд (число за месяц i). */
  compute?: (i: number) => number;
  /** Агрегат в чипе: сумма (Σ) или среднее («ср.»). */
  agg?: "sum" | "avg";
  /** Юнит после агрегата: ₽, $, шт… */
  unit?: string;
}

const num = (v: string | undefined): number => {
  if (!v) return 0;
  const x = Number(String(v).replace(/[\s  ]/g, "").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
};

const NBSP = " ";
const fmtInt = (n: number): string => {
  const r = Math.round(n);
  const s = String(Math.abs(r)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return (r < 0 ? "−" : "") + s;
};
/** Крупные суммы в чипе — «12,4 млн». */
const fmtAgg = (n: number): string =>
  Math.abs(n) >= 1e6 ? (n / 1e6).toFixed(2).replace(".", ",") + NBSP + "млн" : fmtInt(n);

/** Нормализация вставленного значения: пробелы прочь, запятая → точка. */
const norm = (x: string): string => x.trim().replace(/[\s  ]/g, "").replace(",", ".");

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

export function MonthlyGrid({ n, rows, hint = true }: { n: number; rows: MonthlyRow[]; hint?: boolean }) {
  const toast = useToast();
  const [flash, setFlash] = useState<Set<string>>(new Set());
  const [fillRow, setFillRow] = useState<MonthlyRow | null>(null);
  const [fillValue, setFillValue] = useState("");
  const flashTimer = useRef<number>();

  useEffect(() => () => window.clearTimeout(flashTimer.current), []);

  const get = (row: MonthlyRow, i: number) => row.values?.[i] ?? "";

  const setCell = (row: MonthlyRow, i: number, val: string) => {
    row.onChange?.(Array.from({ length: n }, (_, k) => (k === i ? val : get(row, k))));
  };

  const onPaste = (row: MonthlyRow, i: number, e: ClipboardEvent<HTMLInputElement>) => {
    const parts = e.clipboardData.getData("text").split(/[\t;\n\r]+/).map((p) => p.trim()).filter(Boolean);
    if (parts.length <= 1) return; // одно значение — обычная вставка
    e.preventDefault();
    row.onChange?.(
      Array.from({ length: n }, (_, k) =>
        k >= i && parts[k - i] !== undefined ? norm(parts[k - i]) : get(row, k),
      ),
    );
    const filled = Math.min(parts.length, n - i);
    setFlash(new Set(Array.from({ length: filled }, (_, k) => `${row.key}-${i + k}`)));
    window.clearTimeout(flashTimer.current);
    flashTimer.current = window.setTimeout(() => setFlash(new Set()), 2600);
    toast(`Вставлено из Excel: ${filled} ${plural(filled, "значение", "значения", "значений")}`, { kind: "success" });
  };

  const aggChip = (row: MonthlyRow): string => {
    const unit = row.unit ? NBSP + row.unit : "";
    if (row.compute) {
      let sum = 0;
      for (let i = 0; i < n; i++) sum += row.compute(i);
      return `Σ ${fmtAgg(sum)}${unit}`;
    }
    const vals = Array.from({ length: n }, (_, i) => num(get(row, i)));
    if (row.agg === "avg") {
      const nz = vals.filter((x) => x !== 0);
      const avg = nz.length ? nz.reduce((a, c) => a + c, 0) / nz.length : 0;
      return `ср. ${fmtInt(avg)}${unit}`;
    }
    return `Σ ${fmtAgg(vals.reduce((a, c) => a + c, 0))}${unit}`;
  };

  const confirmFill = () => {
    if (fillRow) fillRow.onChange?.(Array.from({ length: n }, () => norm(fillValue)));
    setFillRow(null);
  };

  return (
    <div>
      {hint && (
        <div className="mgrid-hint">
          <span style={{ fontSize: 13 }}>⊞</span>
          Вставьте диапазон из Excel в любую ячейку · Σ и среднее считаются автоматически
        </div>
      )}
      <div className="mgrid-wrap fe-scroll">
        <div className="mgrid-inner">
          <div className="mgrid-row">
            <div className="mgrid-corner">Период{NBSP}→</div>
            {Array.from({ length: n }, (_, i) => (
              <div key={i} className="mgrid-month">
                М{i + 1}
              </div>
            ))}
          </div>

          {rows.map((row) => {
            const ro = !!row.compute;
            return (
              <div key={row.key} className="mgrid-row">
                <div className={"mgrid-label" + (ro ? " mgrid-label--ro" : "")}>
                  <div className={"mgrid-title" + (ro ? " mgrid-title--ro" : "")}>{row.title}</div>
                  <div className="mgrid-sum">{aggChip(row)}</div>
                  {!ro && (
                    <button
                      type="button"
                      className="mgrid-fill"
                      onClick={() => {
                        setFillValue(get(row, 0));
                        setFillRow(row);
                      }}
                    >
                      ↘ заполнить все
                    </button>
                  )}
                </div>
                {Array.from({ length: n }, (_, i) =>
                  ro ? (
                    <div key={i} className="mgrid-rocell">
                      {row.compute!(i) ? fmtInt(row.compute!(i)) : "—"}
                    </div>
                  ) : (
                    <input
                      key={i}
                      className={"mgrid-cell" + (flash.has(`${row.key}-${i}`) ? " mgrid-cell--flash" : "")}
                      inputMode="decimal"
                      title={`Месяц ${i + 1}`}
                      value={get(row, i)}
                      onChange={(e) => setCell(row, i, e.target.value)}
                      onPaste={(e) => onPaste(row, i, e)}
                    />
                  ),
                )}
              </div>
            );
          })}
        </div>
      </div>

      <Modal
        open={!!fillRow}
        onClose={() => setFillRow(null)}
        title="Заполнить все месяцы"
        sub={fillRow ? `Значение будет записано во все ${n} ячеек ряда «${fillRow.title}».` : undefined}
        maxWidth={380}
        actions={
          <>
            <Button variant="ghost" onClick={() => setFillRow(null)}>
              Отмена
            </Button>
            <Button onClick={confirmFill}>Заполнить</Button>
          </>
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            confirmFill();
          }}
        >
          <input
            className="input"
            style={{ width: "100%", fontFamily: "var(--font-mono)", textAlign: "right" }}
            inputMode="decimal"
            autoFocus
            value={fillValue}
            onChange={(e) => setFillValue(e.target.value)}
          />
        </form>
      </Modal>
    </div>
  );
}
