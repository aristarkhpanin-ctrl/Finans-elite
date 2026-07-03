import type { CalcResponse, StatementOut } from "./api/calc";
import { SUBTOTALS } from "./components/StatementTable";
import { fmtMoney, fmtTable, percent, ratio } from "./format";

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

// PDF: A4-альбом, встроенный шрифт с кириллицей (DejaVu subset), таблицы отчётов с
// переносом колонок по месяцам. jsPDF/autotable/шрифт — лениво (только по клику).
export async function downloadPdf(filename: string, result: CalcResponse, projectName: string): Promise<void> {
  const [{ jsPDF }, autoTableMod, fontMod] = await Promise.all([
    import("jspdf"),
    import("jspdf-autotable"),
    import("./pdfFont"),
  ]);
  const autoTable = autoTableMod.default;
  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  doc.addFileToVFS("DejaVuSans.ttf", fontMod.DEJAVU_SANS_BASE64);
  doc.addFont("DejaVuSans.ttf", "DejaVu", "normal");
  doc.setFont("DejaVu");

  const months = Array.from({ length: result.n }, (_, i) => `М${i + 1}`);
  const m = result.metrics;
  const finalY = () => (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY;

  doc.setFontSize(15);
  doc.text(projectName || "Проект", 12, 14);
  doc.setFontSize(9);
  doc.setTextColor(120);
  doc.text(`Финансовая модель · ${result.n} мес · движок ${result.engine_version}`, 12, 20);
  doc.setTextColor(20);

  autoTable(doc, {
    startY: 25,
    styles: { font: "DejaVu", fontSize: 9, textColor: 20 },
    // Только regular-начертание встроено → заголовки тоже normal (акцент — заливкой).
    headStyles: { font: "DejaVu", fontStyle: "normal", fillColor: [19, 138, 69], textColor: 255 },
    head: [["NPV", "IRR (год)", "PI", "Окупаемость, мес."]],
    body: [[
      fmtMoney(m.npv),
      m.irr_annual != null ? percent(m.irr_annual, 1) : "—",
      m.pi != null ? ratio(m.pi) : "—",
      m.pb_months != null ? String(m.pb_months) : "—",
    ]],
  });

  const statements: Array<[string, StatementOut, Set<string>]> = [
    ["Отчёт о прибылях и убытках", result.income, SUBTOTALS.income],
    ["Отчёт о движении денежных средств", result.cashflow, SUBTOTALS.cashflow],
    ["Баланс", result.balance, SUBTOTALS.balance],
    ["Использование прибыли", result.profit_use, SUBTOTALS.profit_use],
  ];

  for (const [title, stmt, subs] of statements) {
    let y = finalY() + 9;
    if (y > doc.internal.pageSize.getHeight() - 24) {
      doc.addPage();
      y = 16;
    }
    doc.setFontSize(11);
    doc.text(title, 12, y);
    autoTable(doc, {
      startY: y + 2,
      margin: { left: 12, right: 12 },
      styles: { font: "DejaVu", fontSize: 6.5, cellPadding: 0.8, textColor: 20, halign: "right" },
      headStyles: { font: "DejaVu", fontStyle: "normal", fillColor: [235, 235, 235], textColor: 20, halign: "right" },
      columnStyles: { 0: { cellWidth: 11, halign: "left" }, 1: { cellWidth: 42, halign: "left" } },
      head: [["Код", "Статья", ...months]],
      body: stmt.lines.map((l) => [l.code, l.label, ...l.values.map((v) => fmtTable(v).text)]),
      didParseCell: (data) => {
        const code = data.section === "body" ? stmt.lines[data.row.index]?.code : undefined;
        if (code && subs.has(code)) data.cell.styles.fillColor = [244, 244, 244];
      },
      horizontalPageBreak: true,
      horizontalPageBreakRepeat: 1,
    });
  }

  doc.save(filename);
}
