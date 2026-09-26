// Импорт/шаблон рядов продаж из Excel (gap 5.3). Round-trip: приложение генерирует
// XLSX-шаблон (продукты × месяцы, ряды «Объём»/«Цена»), пользователь правит и загружает
// обратно. К расчётному ядру отношения не имеет — только правит модель (operating_plan).
import type { OperatingPlan, SalesLine } from "./api/model";

/** Ячейка XLSX для write-excel-file (совместима с типами export.ts). */
type XCell = {
  value: string | number;
  type: StringConstructor | NumberConstructor;
  fontWeight?: "bold";
  format?: string;
};

// Метки рядов показателя в шаблоне (col 1). Распознаём по префиксу без учёта регистра.
export const ROW_VOLUME = "Объём";
export const ROW_PRICE = "Цена";
const HEADER = ["Продукт", "Показатель"];

const num = (v: string | undefined): number => {
  const x = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
};

/** Значение ячейки импорта → строка модели (число нормализуется; пусто → «0»). */
function cellToStr(v: unknown): string {
  if (v == null || v === "") return "0";
  if (typeof v === "number") return String(v);
  const s = String(v).trim().replace(",", ".");
  const x = Number(s);
  return Number.isFinite(x) ? String(x) : "0";
}

/** Привести ряд к длине n (обрезать/дополнить «0») — синхронно с горизонтом. */
function fit(values: string[], n: number): string[] {
  const out = values.slice(0, n);
  while (out.length < n) out.push("0");
  return out;
}

/** Строки шаблона (заголовок + два ряда на продукт): «Продукт | Показатель | М1…Мn». */
export function buildSalesTemplate(operating: OperatingPlan, n: number): XCell[][] {
  const head = (v: string): XCell => ({ value: v, type: String, fontWeight: "bold" });
  const text = (v: string): XCell => ({ value: v, type: String });
  const cell = (v: string): XCell => ({ value: num(v), type: Number, format: "#,##0.####" });
  const months = Array.from({ length: n }, (_, i) => `М${i + 1}`);
  const name = (id: string) => operating.products.find((p) => p.id === id)?.name ?? id;

  const rows: XCell[][] = [[...HEADER.map(head), ...months.map(head)]];
  for (const line of operating.sales) {
    const nm = name(line.product_id);
    rows.push([text(nm), text(ROW_VOLUME), ...fit(line.volume, n).map(cell)]);
    rows.push([text(nm), text(ROW_PRICE), ...fit(line.price, n).map(cell)]);
  }
  return rows;
}

export interface ApplyResult {
  operating: OperatingPlan;
  matched: number;         // сколько строк продаж обновлено
  skipped: string[];       // имена продуктов из файла, которых нет в модели
  ignored: number;         // строки файла с нераспознанным показателем
}

/**
 * Наложить разобранные строки XLSX на план: обновляет `volume`/`price` строк продаж по
 * совпадению **имени продукта** (без учёта регистра/пробелов). Прочие поля строки и
 * остальная модель не трогаются. Продукт из файла без пары в модели → `skipped`.
 */
export function applySalesRows(
  operating: OperatingPlan,
  rows: (string | number | null)[][],
  n: number,
): ApplyResult {
  const norm = (s: unknown) => String(s ?? "").trim().toLowerCase();
  const nameOf = (line: SalesLine) =>
    operating.products.find((p) => p.id === line.product_id)?.name ?? "";
  // Индекс строк продаж по нормализованному имени продукта.
  const byName = new Map<string, number>();
  operating.sales.forEach((line, i) => byName.set(norm(nameOf(line)), i));

  // Патчи по индексу строки: собираем объём/цену, применяем разом (иммутабельно).
  const patch = new Map<number, Partial<SalesLine>>();
  const skipped = new Set<string>();
  let ignored = 0;

  for (let r = 0; r < rows.length; r++) {
    const row = rows[r];
    if (!row || row.length === 0) continue;
    const label = norm(row[0]);
    const metric = norm(row[1]);
    // Пропускаем строку заголовка (совпадает с «продукт»/пусто).
    if (r === 0 && label === norm(HEADER[0])) continue;
    if (label === "" && metric === "") continue;

    const isVol = metric.startsWith(norm(ROW_VOLUME));
    const isPrice = metric.startsWith(norm(ROW_PRICE));
    if (!isVol && !isPrice) {
      ignored++;
      continue;
    }
    const idx = byName.get(label);
    if (idx === undefined) {
      skipped.add(String(row[0] ?? "").trim() || "(без имени)");
      continue;
    }
    const values = fit(row.slice(2).map(cellToStr), n);
    patch.set(idx, { ...patch.get(idx), ...(isVol ? { volume: values } : { price: values }) });
  }

  if (patch.size === 0) {
    return { operating, matched: 0, skipped: [...skipped], ignored };
  }
  const sales = operating.sales.map((line, i) =>
    patch.has(i) ? { ...line, ...patch.get(i)! } : line,
  );
  return { operating: { ...operating, sales }, matched: patch.size, skipped: [...skipped], ignored };
}

/** Скачать XLSX-шаблон рядов продаж (write-excel-file грузится лениво). */
export async function downloadSalesTemplate(
  filename: string,
  operating: OperatingPlan,
  n: number,
): Promise<void> {
  const writeXlsxFile = (await import("write-excel-file/browser")).default;
  const cols = [{ width: 28 }, { width: 12 }, ...Array.from({ length: n }, () => ({ width: 11 }))];
  await writeXlsxFile([{ data: buildSalesTemplate(operating, n), sheet: "Продажи", columns: cols }])
    .toFile(filename);
}

/** Прочитать XLSX-файл и наложить ряды продаж на план (read-excel-file лениво). */
export async function parseSalesXlsx(
  file: File | Blob,
  operating: OperatingPlan,
  n: number,
): Promise<ApplyResult> {
  const readXlsxFile = (await import("read-excel-file")).default;
  const rows = (await readXlsxFile(file as File)) as (string | number | null)[][];
  return applySalesRows(operating, rows, n);
}
