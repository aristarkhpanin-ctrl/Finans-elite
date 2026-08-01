// Выгрузка результатов анализа (Финанс-Аудит, v2): аналитическая форма, тренды,
// коэффициенты, диагностика, свои показатели — по листу на раздел.
//
// Здесь только сборка листов из готового ответа `/analyze` — ничего не пересчитывается,
// поэтому файл не может разойтись с экраном. Ключевое соглашение аналитики сохраняется и
// в выгрузке: **неопределённый показатель (нулевая база) остаётся пустой ячейкой**, а не
// нулём — ноль в Excel читался бы как посчитанное значение.
import type { AuditAnalysis, AuditLineOut } from "./api/audit";
import { RATIO_GROUPS } from "./api/audit";

/** Ячейка XLSX для write-excel-file. */
type XCell = {
  value: string | number;
  type: StringConstructor | NumberConstructor;
  fontWeight?: "bold";
  format?: string;
} | null;

const MONEY = "#,##0.00";
const RATIO = "0.0000";
const PCT = "0.0%";

const head = (v: string): XCell => ({ value: v, type: String, fontWeight: "bold" });
const text = (v: string, bold?: boolean): XCell =>
  ({ value: v, type: String, ...(bold ? { fontWeight: "bold" as const } : {}) });
const num = (v: number, format: string, bold?: boolean): XCell =>
  ({ value: v, type: Number, format, ...(bold ? { fontWeight: "bold" as const } : {}) });

/** Строка-Decimal → число; пусто/невалидно → null («не определён»). */
const dec = (v: string | null | undefined): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const x = Number(String(v).replace(",", "."));
  return Number.isFinite(x) ? x : null;
};

/** Значение или пустая ячейка: «не определён» не подменяется нулём. */
const cell = (v: string | null | undefined, format: string, bold?: boolean): XCell => {
  const x = dec(v);
  return x === null ? null : num(x, format, bold);
};

/** Показатели-доли выводятся процентным форматом, денежные — денежным (как на экране). */
const PCT_RATIOS = /^(Рентабельность|Коэффициент автономии|Суммарные обязательства)/;
const MONEY_RATIOS = /^(Чистый оборотный капитал)/;
const ratioFormat = (name: string): string =>
  MONEY_RATIOS.test(name) ? MONEY : PCT_RATIOS.test(name) ? PCT : RATIO;

/** Подписи зон скоринга и статусов нормативов (зеркало вкладки «Диагностика»). */
const ZONE_LABEL: Record<string, string> = {
  safe: "устойчивость", grey: "неопределённость", distress: "высокий риск",
};
const STATUS_LABEL: Record<string, string> = {
  good: "норма", warn: "внимание", risk: "вне норматива",
};
const LIGHT_LABEL: Record<string, string> = {
  ok: "Устойчивое состояние", warning: "Есть зоны внимания", risk: "Признаки неустойчивости",
};

const headerRow = (first: string, periods: string[]): XCell[] =>
  [head(first), ...periods.map(head)];

/** Лист аналитической формы: баланс и ОПУ подряд, подытоги — жирным. */
export function formSheet(a: AuditAnalysis): XCell[][] {
  if (a.balance.length === 0 && a.income.length === 0) return [];
  const rows: XCell[][] = [headerRow("Статья", a.periods)];
  const section = (title: string, lines: AuditLineOut[]) => {
    rows.push([head(title), ...a.periods.map(() => head(""))]);
    for (const ln of lines) {
      rows.push([text(ln.label, ln.subtotal), ...ln.values.map((v) => cell(v, MONEY, ln.subtotal))]);
    }
  };
  section("АНАЛИТИЧЕСКИЙ БАЛАНС", a.balance);
  section("ОТЧЁТ О ФИНАНСОВЫХ РЕЗУЛЬТАТАХ", a.income);
  return rows;
}

/**
 * Лист трендов: на статью две строки — абсолютное изменение и темп к предыдущему периоду.
 * Первый период — база, у него изменения нет (пустая ячейка, не ноль).
 */
export function trendsSheet(a: AuditAnalysis): XCell[][] {
  if (a.horizontal.length === 0) return [];
  const rows: XCell[][] = [[head("Статья"), head("Показатель"), ...a.periods.map(head)]];
  for (const t of a.horizontal) {
    rows.push([text(t.label), text("Изменение"), ...t.delta.map((v) => cell(v, MONEY))]);
    rows.push([text(""), text("Темп прироста"), ...t.rate.map((v) => cell(v, PCT))]);
  }
  return rows;
}

/** Лист структуры: доля статьи в базе (баланс — от актива, ОПУ — от выручки). */
export function structureSheet(a: AuditAnalysis): XCell[][] {
  if (a.vertical.length === 0) return [];
  const rows: XCell[][] = [headerRow("Статья", a.periods)];
  for (const s of a.vertical) {
    rows.push([text(s.label), ...s.share.map((v) => cell(v, PCT))]);
  }
  return rows;
}

/** Лист коэффициентов: группы подряд, порядок — как на вкладке «Коэффициенты». */
export function ratiosSheet(a: AuditAnalysis): XCell[][] {
  const groups = RATIO_GROUPS.filter(([key]) => Object.keys(a.ratios[key] ?? {}).length > 0);
  if (groups.length === 0) return [];
  const rows: XCell[][] = [headerRow("Показатель", a.periods)];
  for (const [key, title] of groups) {
    const group = a.ratios[key];
    rows.push([head(title.toUpperCase()), ...a.periods.map(() => head(""))]);
    for (const [name, values] of Object.entries(group)) {
      const fmt = ratioFormat(name);
      rows.push([text(name), ...values.map((v) => cell(v, fmt))]);
    }
  }
  return rows;
}

/**
 * Лист диагностики: «светофор», скоринговые модели (значение + зона по периодам) и
 * оценки коэффициентов против нормативов. Пусто, если диагностика не считалась.
 */
export function diagnosticsSheet(a: AuditAnalysis): XCell[][] {
  const d = a.diagnostics;
  if (!d) return [];
  const rows: XCell[][] = [
    [head("Оценка"), text(LIGHT_LABEL[d.light] ?? d.light)],
    [head("Пояснение"), text(d.summary)],
    [],
  ];
  if (d.scores.length > 0) {
    rows.push([head("Модель"), head("Показатель"), ...a.periods.map(head)]);
    for (const s of d.scores) {
      rows.push([text(s.name), text("Значение"), ...s.values.map((v) => cell(v, RATIO))]);
      rows.push([text(""), text("Зона"), ...s.zones.map((z) => text(z ? ZONE_LABEL[z] ?? z : "—"))]);
      if (s.note) rows.push([text(""), text(s.note)]);
    }
    rows.push([]);
  }
  if (d.assessments.length > 0) {
    rows.push([head("Показатель"), head("Группа"), ...a.periods.map(head)]);
    for (const as of d.assessments) {
      rows.push([
        text(as.name),
        text(as.group),
        ...as.status.map((st) => text(st ? STATUS_LABEL[st] ?? st : "—")),
      ]);
    }
  }
  return rows;
}

/** Лист своих показателей (вкладка «Методики»); ошибка формулы выносится в колонку. */
export function metricsSheet(a: AuditAnalysis): XCell[][] {
  if (a.user_metrics.length === 0) return [];
  const rows: XCell[][] = [[head("Показатель"), ...a.periods.map(head), head("Ошибка")]];
  for (const u of a.user_metrics) {
    rows.push([text(u.name), ...u.values.map((v) => cell(v, RATIO)), text(u.error ?? "")]);
  }
  return rows;
}

/** Лист заключения: абзацы автотекста по строкам (для чтения и копирования). */
export function opinionSheet(a: AuditAnalysis): XCell[][] {
  const blocks = a.opinion.split("\n\n").filter((b) => b.trim() !== "");
  return blocks.length === 0 ? [] : [[head("Заключение")], ...blocks.map((b) => [text(b)])];
}

/** Лист → описание для write-excel-file; пустые разделы не попадают в файл. */
type Sheet = { data: XCell[][]; sheet: string; columns: { width: number }[] };

/** Все листы выгрузки в порядке вкладок анализа (пустые разделы пропущены). */
export function buildAuditWorkbook(a: AuditAnalysis): Sheet[] {
  const p = a.periods.map(() => ({ width: 15 }));
  const plan: Array<[string, XCell[][], { width: number }[]]> = [
    ["Аналитическая форма", formSheet(a), [{ width: 44 }, ...p]],
    ["Тренды", trendsSheet(a), [{ width: 44 }, { width: 18 }, ...p]],
    ["Структура", structureSheet(a), [{ width: 44 }, ...p]],
    ["Коэффициенты", ratiosSheet(a), [{ width: 44 }, ...p]],
    ["Диагностика", diagnosticsSheet(a), [{ width: 44 }, { width: 22 }, ...p]],
    ["Методики", metricsSheet(a), [{ width: 44 }, ...p, { width: 30 }]],
    ["Заключение", opinionSheet(a), [{ width: 120 }]],
  ];
  return plan
    .filter(([, data]) => data.length > 0)
    .map(([sheet, data, columns]) => ({ sheet, data, columns }));
}

/** Скачать выгрузку анализа (write-excel-file грузится лениво — по клику). */
export async function downloadAuditXlsx(filename: string, a: AuditAnalysis): Promise<void> {
  const sheets = buildAuditWorkbook(a);
  // Пустая книга — не файл без листов, а сигнал, что выгружать нечего.
  if (sheets.length === 0) throw new Error("Анализ пуст — выгружать нечего");
  const writeXlsxFile = (await import("write-excel-file/browser")).default;
  await writeXlsxFile(sheets).toFile(filename);
}
