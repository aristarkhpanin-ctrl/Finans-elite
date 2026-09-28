// Импорт издержек и персонала из Excel (пакет G, G13). Round-trip, как у рядов продаж:
// приложение даёт книгу-шаблон из трёх листов, человек правит её и загружает обратно.
//
// Правила (все — в отчёте импорта, а не в догадках пользователя):
//
// * сопоставление — **по имени** (без регистра и лишних пробелов): найденное обновляется,
//   недостающее **создаётся** — отдельным списком, с **названными умолчаниями**, которые
//   стоит проверить (отсрочки, функция, сроки). Статьи модели, которых нет в файле, не
//   удаляются: импорт дописывает и правит, а не заменяет раздел;
// * строка листа — полное описание статьи: пустая ячейка получает умолчание, и оно
//   названо; нечитаемая — строка не применяется, и сказано, где (`xlsxCells`);
// * повтор имени в файле — берётся первая строка, повтор назван;
// * листа нет в книге — раздел модели не тронут, и это тоже сказано.
//
// К расчётному ядру отношения не имеет: правит только модель, как ручной ввод.
import {
  COST_FUNCTION_LABELS,
  type CostFunction,
  type DirectCostKind,
  type DirectCostLine,
  type FixedCostLine,
  type OperatingPlan,
  type StaffPosition,
} from "./api/model";
import { cellNumber, cellSeries, cellText, matchKey } from "./xlsxCells";

export const SHEET_DIRECT = "Прямые издержки";
export const SHEET_FIXED = "Постоянные издержки";
export const SHEET_STAFF = "Персонал";

export const KIND_LABELS: Record<DirectCostKind, string> = {
  materials: "Материалы",
  piece_wages: "Сдельная оплата",
};

type StaffFunction = "staff_admin" | "staff_production" | "staff_marketing";

/** Подписи функций штата — те же, что в селекте вкладки «Издержки». */
export const STAFF_FUNCTION_LABELS: Record<StaffFunction, string> = {
  staff_admin: "Административный",
  staff_production: "Производственный",
  staff_marketing: "Маркетинговый",
};

const STAFF_HEADER = ["Должность", "Оклад в месяц", "Численность", "Первый месяц",
                      "Последний месяц", "Функция"];

/** Умолчания, которые получают созданные строки и пустые ячейки, — едут в отчёт. */
export const DEFAULTS: Record<string, string> = {
  [SHEET_DIRECT]: "Созданные статьи: оплата без отсрочки, закупка без опережения, в рублях. " +
    "Пустой «Вид» — «Материалы», пустой месяц — ноль.",
  [SHEET_FIXED]: "Созданные статьи: оплата без отсрочки, уменьшают налоговую базу (не «из " +
    "прибыли»), в рублях. Пустая «Функция» — «Административные», пустой месяц — ноль.",
  [SHEET_STAFF]: "Созданные должности: выплата без отсрочки. Пустые ячейки: численность — 1, " +
    "первый месяц — 1-й, последний — до конца горизонта, функция — административная. " +
    "Оклад обязателен.",
};

/** Ячейка XLSX для write-excel-file (как в salesXlsx). */
type XCell = {
  value: string | number;
  type: StringConstructor | NumberConstructor;
  fontWeight?: "bold";
  format?: string;
};

export interface SheetBook {
  sheet: string;
  data: XCell[][];
  columns: { width: number }[];
}

const head = (v: string): XCell => ({ value: v, type: String, fontWeight: "bold" });
const text = (v: string): XCell => ({ value: v, type: String });
const numberCell = (v: string | number | undefined | null): XCell => {
  const x = cellNumber(v ?? "");
  return { value: x === undefined || Number.isNaN(x) ? 0 : x, type: Number, format: "#,##0.####" };
};

/** Ряд модели, приведённый к горизонту (короткий дополняется нулями, как в движке). */
function fitSeries(values: string[], n: number): string[] {
  const out = values.slice(0, n);
  while (out.length < n) out.push("0");
  return out;
}

/** Книга-шаблон: три листа с текущими статьями — её же и загружают обратно. */
export function buildCostsWorkbook(operating: OperatingPlan, n: number): SheetBook[] {
  const months = Array.from({ length: n }, (_, i) => `М${i + 1}`);
  const seriesCols = [{ width: 30 }, { width: 18 }, ...months.map(() => ({ width: 11 }))];

  const direct: XCell[][] = [[head("Статья"), head("Вид"), ...months.map(head)]];
  for (const d of operating.direct_costs) {
    direct.push([text(d.name), text(KIND_LABELS[d.kind] ?? KIND_LABELS.materials),
                 ...fitSeries(d.amount, n).map(numberCell)]);
  }
  const fixed: XCell[][] = [[head("Статья"), head("Функция"), ...months.map(head)]];
  for (const f of operating.fixed_costs) {
    fixed.push([text(f.name), text(COST_FUNCTION_LABELS[f.function] ?? COST_FUNCTION_LABELS.admin),
                ...fitSeries(f.amount, n).map(numberCell)]);
  }
  const staff: XCell[][] = [STAFF_HEADER.map(head)];
  for (const s of operating.staff ?? []) {
    const fn = (s.function ?? "staff_admin") as StaffFunction;
    staff.push([
      text(s.name), numberCell(s.monthly_salary), numberCell(s.headcount ?? "1"),
      { value: (s.start_month ?? 0) + 1, type: Number },
      // Последний месяц в модели — граница «не включая» от нуля, то есть то же число,
      // что последний месяц работы от единицы. Пусто — до конца горизонта.
      s.end_month == null ? text("") : { value: s.end_month, type: Number },
      text(STAFF_FUNCTION_LABELS[fn] ?? STAFF_FUNCTION_LABELS.staff_admin),
    ]);
  }
  return [
    { sheet: SHEET_DIRECT, data: direct, columns: seriesCols },
    { sheet: SHEET_FIXED, data: fixed, columns: seriesCols },
    { sheet: SHEET_STAFF, data: staff,
      columns: [{ width: 30 }, { width: 15 }, { width: 13 }, { width: 14 }, { width: 16 },
                { width: 18 }] },
  ];
}

export interface SheetReport {
  sheet: string;
  /** Листа нет в книге — раздел модели не тронут. */
  absent: boolean;
  updated: string[];
  created: string[];
  /** Умолчания созданных строк и пустых ячеек — их стоит проверить. */
  defaults: string;
  /** Строки, которые не применены, — с причиной и номером строки листа. */
  problems: string[];
}

export interface CostsImport {
  operating: OperatingPlan;
  sheets: SheetReport[];
  /** Хоть что-то обновлено или создано. */
  changed: boolean;
}

type Parsed<T> = { line: T } | { error: string };

/** Подпись → код по словарю подписей (без регистра); неизвестная — `undefined`. */
function byLabel<K extends string>(labels: Record<K, string>, value: string): K | undefined {
  const key = matchKey(value);
  return (Object.keys(labels) as K[]).find((k) => matchKey(labels[k]) === key || k === key);
}

/**
 * Общая часть трёх листов: заголовок и пустые строки пропускаются, имя сопоставляется,
 * повторы и нечитаемое называются, найденное заменяется, недостающее — дописывается.
 */
function applyNamed<T extends { name: string }>(
  sheet: string, lines: T[], rows: unknown[][] | undefined, firstHeader: string,
  parse: (row: unknown[], name: string, existing: T | undefined) => Parsed<T>,
): { lines: T[]; report: SheetReport } {
  const report: SheetReport = { sheet, absent: rows === undefined, updated: [], created: [],
                                defaults: DEFAULTS[sheet] ?? "", problems: [] };
  if (!rows) return { lines, report };

  const out = [...lines];
  const firstIndex = new Map<string, number>();
  const dupInModel = new Set<string>();
  lines.forEach((l, i) => {
    const key = matchKey(l.name);
    if (firstIndex.has(key)) dupInModel.add(key);
    else firstIndex.set(key, i);
  });
  const seen = new Set<string>();

  rows.forEach((row, r) => {
    const at = `строка ${r + 1}`;
    if (!row || row.every((c) => cellText(c) === "")) return;              // пустая строка
    if (r === 0 && matchKey(row[0]) === matchKey(firstHeader)) return;       // заголовок
    const name = cellText(row[0]);
    if (!name) {
      report.problems.push(`${at}: нет названия — строка не применена`);
      return;
    }
    const key = matchKey(name);
    if (seen.has(key)) {
      report.problems.push(`${at}: «${name}» уже была выше — взята первая строка`);
      return;
    }
    seen.add(key);
    const idx = firstIndex.get(key);
    const parsed = parse(row, name, idx === undefined ? undefined : out[idx]);
    if ("error" in parsed) {
      report.problems.push(`${at} («${name}»): ${parsed.error} — строка не применена`);
      return;
    }
    if (idx === undefined) {
      out.push(parsed.line);
      report.created.push(name);
    } else {
      out[idx] = parsed.line;
      report.updated.push(out[idx].name);
      if (dupInModel.has(key)) {
        report.problems.push(`в модели несколько статей «${out[idx].name}» — обновлена первая`);
      }
    }
  });
  return { lines: out, report };
}

/** Наложить разобранные листы на план. `sheets` — строки листов по их названиям. */
export function applyCostsWorkbook(
  operating: OperatingPlan, sheets: Record<string, unknown[][] | undefined>, n: number,
): CostsImport {
  const direct = applyNamed<DirectCostLine>(
    SHEET_DIRECT, operating.direct_costs, sheets[SHEET_DIRECT], "Статья",
    (row, name, existing) => {
      const kindText = cellText(row[1]);
      const kind = kindText ? byLabel(KIND_LABELS, kindText) : "materials";
      if (!kind) {
        return { error: `вид «${kindText}» не распознан — «Материалы» или «Сдельная оплата»` };
      }
      const series = cellSeries(row.slice(2), n);
      if ("error" in series) return series;
      const base: DirectCostLine = existing ??
        { name, kind, amount: [], payment_delay_months: 0, stock_lead_months: 0 };
      return { line: { ...base, kind, amount: series.values } };
    });

  const fixed = applyNamed<FixedCostLine>(
    SHEET_FIXED, operating.fixed_costs, sheets[SHEET_FIXED], "Статья",
    (row, name, existing) => {
      const fnText = cellText(row[1]);
      const fn: CostFunction | undefined = fnText ? byLabel(COST_FUNCTION_LABELS, fnText) : "admin";
      if (!fn) {
        return { error: `функция «${fnText}» не распознана — ` +
                        Object.values(COST_FUNCTION_LABELS).map((l) => `«${l}»`).join(", ") };
      }
      const series = cellSeries(row.slice(2), n);
      if ("error" in series) return series;
      const base: FixedCostLine = existing ??
        { name, function: fn, amount: [], payment_delay_months: 0 };
      return { line: { ...base, function: fn, amount: series.values } };
    });

  const staff = applyNamed<StaffPosition>(
    SHEET_STAFF, operating.staff ?? [], sheets[SHEET_STAFF], STAFF_HEADER[0],
    (row, name, existing) => {
      const salary = cellNumber(row[1]);
      if (salary === undefined) return { error: "не задан оклад" };
      if (Number.isNaN(salary) || salary < 0) {
        return { error: `оклад «${cellText(row[1])}» — не число` };
      }
      const head = cellNumber(row[2]);
      if (head !== undefined && (Number.isNaN(head) || head < 0)) {
        return { error: `численность «${cellText(row[2])}» — не число` };
      }
      const first = cellNumber(row[3]);
      if (first !== undefined && (!Number.isInteger(first) || first < 1)) {
        return { error: `первый месяц «${cellText(row[3])}» — нужен номер месяца от 1` };
      }
      const last = cellNumber(row[4]);
      const firstMonth = first ?? 1;
      if (last !== undefined && (!Number.isInteger(last) || last < firstMonth)) {
        return { error: `последний месяц «${cellText(row[4])}» — номер месяца не раньше первого` };
      }
      const fnText = cellText(row[5]);
      const fn = fnText ? byLabel(STAFF_FUNCTION_LABELS, fnText) : "staff_admin";
      if (!fn) {
        return { error: `функция «${fnText}» не распознана — ` +
                        Object.values(STAFF_FUNCTION_LABELS).map((l) => `«${l}»`).join(", ") };
      }
      const base: StaffPosition = existing ?? { name, monthly_salary: "0" };
      return { line: { ...base, monthly_salary: String(salary), headcount: String(head ?? 1),
                       start_month: firstMonth - 1, end_month: last ?? null, function: fn } };
    });

  const sheetsOut = [direct.report, fixed.report, staff.report];
  const changed = sheetsOut.some((s) => s.updated.length + s.created.length > 0);
  if (!changed) return { operating, sheets: sheetsOut, changed };
  return {
    operating: { ...operating, direct_costs: direct.lines, fixed_costs: fixed.lines,
                 staff: staff.lines },
    sheets: sheetsOut,
    changed,
  };
}

/** Скачать книгу-шаблон (write-excel-file грузится лениво). */
export async function downloadCostsTemplate(
  filename: string, operating: OperatingPlan, n: number,
): Promise<void> {
  const writeXlsxFile = (await import("write-excel-file/browser")).default;
  const book = buildCostsWorkbook(operating, n);
  await writeXlsxFile(book.map((s) => ({ data: s.data, sheet: s.sheet, columns: s.columns })))
    .toFile(filename);
}

/** Прочитать книгу и наложить листы на план (read-excel-file грузится лениво). */
export async function parseCostsXlsx(
  file: File | Blob, operating: OperatingPlan, n: number,
): Promise<CostsImport> {
  const { default: readXlsxFile, readSheetNames } = await import("read-excel-file");
  const names = await readSheetNames(file as File);
  const sheets: Record<string, unknown[][]> = {};
  for (const wanted of [SHEET_DIRECT, SHEET_FIXED, SHEET_STAFF]) {
    // Название листа сверяется без регистра и лишних пробелов: переименованный вручную
    // «персонал» — тот же лист, а не повод молча пропустить раздел.
    const actual = names.find((s) => matchKey(s) === matchKey(wanted));
    if (actual) sheets[wanted] = (await readXlsxFile(file as File, { sheet: actual })) as unknown[][];
  }
  return applyCostsWorkbook(operating, sheets, n);
}
