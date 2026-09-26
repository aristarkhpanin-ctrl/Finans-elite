// Импорт/шаблон фактической отчётности из Excel (Финанс-Аудит, фаза F).
// Round-trip: приложение генерирует XLSX-шаблон (строка отчётности × период), пользователь
// заполняет и загружает обратно. Тот же подход, что импорт продаж в первом продукте:
// формат задаёт приложение → не нужно угадывать чужую структуру файла.
import { ASSET_LINES, EQLIAB_LINES, INCOME_LINES, MEMO_LINES, type AuditModel } from "./api/audit";

/** Ячейка XLSX для write-excel-file. */
type XCell = {
  value: string | number;
  type: StringConstructor | NumberConstructor;
  fontWeight?: "bold";
  format?: string;
};

const HEADER = ["Код", "Статья"];

/** Раздел шаблона: подпись, таблица модели и строки каталога. */
interface Section {
  title: string;
  table: "balance" | "income";
  lines: [string, string][];
}

export const SECTIONS: Section[] = [
  { title: "БАЛАНС — АКТИВ", table: "balance", lines: ASSET_LINES },
  { title: "БАЛАНС — ПАССИВ", table: "balance", lines: EQLIAB_LINES },
  { title: "РАСШИФРОВКА (в итог не входит)", table: "balance", lines: MEMO_LINES },
  { title: "ОТЧЁТ О ФИНАНСОВЫХ РЕЗУЛЬТАТАХ", table: "income", lines: INCOME_LINES },
];

/** Код строки → таблица модели, в которую она пишется. */
const TABLE_OF: Record<string, "balance" | "income"> = Object.fromEntries(
  SECTIONS.flatMap((s) => s.lines.map(([code]) => [code, s.table])),
);

const num = (v: string | undefined): number => {
  const x = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
};

/** Значение ячейки импорта → строка модели (число нормализуется; пусто → «0»). */
function cellToStr(v: unknown): string {
  if (v == null || v === "") return "0";
  if (typeof v === "number") return String(v);
  const s = String(v).trim().replace(/\s/g, "").replace(",", ".");
  const x = Number(s);
  return Number.isFinite(x) ? String(x) : "0";
}

/** Привести ряд к числу периодов (обрезать/дополнить нулями). */
function fit(values: string[], n: number): string[] {
  const out = values.slice(0, n);
  while (out.length < n) out.push("0");
  return out;
}

/** Строки шаблона: заголовок + разделы со строками отчётности по периодам. */
export function buildAuditTemplate(model: AuditModel): XCell[][] {
  const head = (v: string): XCell => ({ value: v, type: String, fontWeight: "bold" });
  const text = (v: string): XCell => ({ value: v, type: String });
  const cell = (v: string): XCell => ({ value: num(v), type: Number, format: "#,##0.##" });
  const periods = model.periods.map((p, i) => p.label || `Период ${i + 1}`);

  const rows: XCell[][] = [[...HEADER.map(head), ...periods.map(head)]];
  for (const section of SECTIONS) {
    rows.push([head(""), head(section.title), ...periods.map(() => head(""))]);
    for (const [code, label] of section.lines) {
      const values = fit(model[section.table][code] ?? [], periods.length);
      rows.push([text(code), text(label), ...values.map(cell)]);
    }
  }
  return rows;
}

export interface AuditApplyResult {
  model: AuditModel;
  matched: number;      // сколько строк отчётности обновлено
  skipped: string[];    // коды/названия из файла, которых нет в каталоге
  ignored: number;      // служебные строки файла (заголовки разделов и пр.)
}

/**
 * Наложить разобранные строки XLSX на модель: обновляет значения строк отчётности по
 * **коду** (первая колонка), а при его отсутствии — по названию статьи. Периоды и прочие
 * поля модели не трогаются: структуру задаёт субъект, файл приносит только числа.
 */
export function applyAuditRows(
  model: AuditModel,
  rows: (string | number | null)[][],
): AuditApplyResult {
  const n = model.periods.length;
  const norm = (s: unknown) => String(s ?? "").trim().toLowerCase();
  const byLabel = new Map<string, string>();
  for (const section of SECTIONS) {
    for (const [code, label] of section.lines) byLabel.set(norm(label), code);
  }

  const patch: Record<string, Record<string, string[]>> = { balance: {}, income: {} };
  const skipped = new Set<string>();
  let matched = 0;
  let ignored = 0;

  for (const row of rows) {
    if (!row || row.length === 0) continue;
    const rawCode = String(row[0] ?? "").trim();
    const rawLabel = String(row[1] ?? "").trim();
    if (!rawCode && !rawLabel) continue;

    // Заголовок таблицы и подписи разделов — служебные строки.
    if (norm(rawCode) === norm(HEADER[0]) || SECTIONS.some((s) => norm(s.title) === norm(rawLabel))) {
      ignored++;
      continue;
    }

    const code = TABLE_OF[rawCode] ? rawCode : byLabel.get(norm(rawLabel));
    if (!code) {
      skipped.add(rawCode || rawLabel);
      continue;
    }
    patch[TABLE_OF[code]][code] = fit(row.slice(2).map(cellToStr), n);
    matched++;
  }

  if (matched === 0) {
    return { model, matched: 0, skipped: [...skipped], ignored };
  }
  return {
    model: {
      ...model,
      balance: { ...model.balance, ...patch.balance },
      income: { ...model.income, ...patch.income },
    },
    matched,
    skipped: [...skipped],
    ignored,
  };
}

/** Скачать XLSX-шаблон отчётности (write-excel-file грузится лениво). */
export async function downloadAuditTemplate(filename: string, model: AuditModel): Promise<void> {
  const writeXlsxFile = (await import("write-excel-file/browser")).default;
  const cols = [{ width: 16 }, { width: 46 },
                ...model.periods.map(() => ({ width: 14 }))];
  await writeXlsxFile([{ data: buildAuditTemplate(model), sheet: "Отчётность", columns: cols }])
    .toFile(filename);
}

/** Прочитать XLSX и наложить отчётность на модель (read-excel-file лениво). */
export async function parseAuditXlsx(file: File | Blob, model: AuditModel): Promise<AuditApplyResult> {
  const readXlsxFile = (await import("read-excel-file")).default;
  const rows = (await readXlsxFile(file as File)) as (string | number | null)[][];
  return applyAuditRows(model, rows);
}
