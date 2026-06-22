import type { CalcResponse, StatementOut } from "./api/calc";

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
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
