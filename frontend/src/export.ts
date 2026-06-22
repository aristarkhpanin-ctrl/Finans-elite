import type { CalcResponse, StatementOut } from "./api/calc";
import { SUBTOTALS } from "./components/StatementTable";

// Экспорт отчётов в CSV (разделитель «;» — Excel RU; UTF-8 BOM для кириллицы).
function csvCell(v: string): string {
  const s = String(v ?? "");
  return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function statementsToCsv(result: CalcResponse): string {
  const months = Array.from({ length: result.n }, (_, i) => `М${i + 1}`);
  const rows: string[][] = [["Раздел", "Код", "Статья", ...months]];
  const add = (title: string, stmt: StatementOut) => {
    for (const l of stmt.lines) rows.push([title, l.code, l.label, ...l.values]);
  };
  add("ОПУ", result.income);
  add("Кэш-фло", result.cashflow);
  add("Баланс", result.balance);
  add("Использование прибыли", result.profit_use);
  return rows.map((r) => r.map(csvCell).join(";")).join("\r\n");
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  triggerDownload(filename, blob);
}

function triggerDownload(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// XLSX: лист на каждый отчёт + лист показателей. write-excel-file грузится лениво (по клику).
type XCell = {
  value: string | number;
  type: StringConstructor | NumberConstructor;
  fontWeight?: "bold";
  format?: string;
};

const head = (v: string): XCell => ({ value: v, type: String, fontWeight: "bold" });
const text = (v: string, bold?: boolean): XCell =>
  ({ value: v, type: String, ...(bold ? { fontWeight: "bold" as const } : {}) });
const num = (v: number, fmt: string, bold?: boolean): XCell =>
  ({ value: v, type: Number, format: fmt, ...(bold ? { fontWeight: "bold" as const } : {}) });

function statementSheet(stmt: StatementOut, subtotals: Set<string>, months: string[]): XCell[][] {
  const rows: XCell[][] = [[head("Код"), head("Статья"), ...months.map(head)]];
  for (const l of stmt.lines) {
    const bold = subtotals.has(l.code);
    rows.push([
      text(l.code, bold),
      text(l.label, bold),
      ...l.values.map((v) => num(Number(v), "#,##0.00", bold)),
    ]);
  }
  return rows;
}

export async function downloadXlsx(filename: string, result: CalcResponse): Promise<void> {
  const writeXlsxFile = (await import("write-excel-file/browser")).default;
  const months = Array.from({ length: result.n }, (_, i) => `М${i + 1}`);
  const m = result.metrics;
  const metrics: XCell[][] = [
    [head("Показатель"), head("Значение")],
    [text("NPV"), num(Number(m.npv), "#,##0.00")],
    [text("IRR (год)"), m.irr_annual ? num(Number(m.irr_annual), "0.0%") : text("—")],
    [text("PI"), m.pi ? num(Number(m.pi), "0.00") : text("—")],
    [text("Окупаемость, мес."), m.pb_months != null ? num(m.pb_months, "0") : text("—")],
  ];

  const stmtCols = [{ width: 8 }, { width: 36 }, ...months.map(() => ({ width: 13 }))];
  await writeXlsxFile([
    { data: statementSheet(result.income, SUBTOTALS.income, months), sheet: "ОПУ", columns: stmtCols },
    { data: statementSheet(result.cashflow, SUBTOTALS.cashflow, months), sheet: "Кэш-фло", columns: stmtCols },
    { data: statementSheet(result.balance, SUBTOTALS.balance, months), sheet: "Баланс", columns: stmtCols },
    { data: statementSheet(result.profit_use, SUBTOTALS.profit_use, months), sheet: "Использование прибыли", columns: stmtCols },
    { data: metrics, sheet: "Показатели", columns: [{ width: 26 }, { width: 18 }] },
  ]).toFile(filename);
}
