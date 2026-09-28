// Разбор ячеек XLSX-импорта (продажи, издержки, персонал — пакет G, G13). Одно правило
// на все листы:
//
// * пусто — «нет значения»: в ряду по месяцам это ноль, в поле — умолчание, и оно
//   названо в отчёте импорта;
// * число — число; текст — по русскому написанию, как его принимает сервер
//   (`calc_core/decimals.py`): «5,0», «1 200,50» — пробел делит разряды **по три цифры**;
// * **нечитаемое не становится нулём.** Строка с ним не применяется, а отчёт называет
//   лист, строку и ячейку. До G13 «сто» и «1 200,50» в текстовой ячейке молча давали 0 —
//   импорт выдумывал число, а человек не знал, что ряд обнулён.
//
// Строже, чем `format.parseModelNumber`: та проверяет поле на экране и не должна
// объявлять ошибкой то, что сервер примет; импорт превращает текст в число, и «1 2»
// здесь — не двенадцать, а вопрос к человеку.

const PLAIN = /^[+-]?\d+(?:[.,]\d+)?$/;
const GROUPED = /^[+-]?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:,\d+)?$/;

/** Число из ячейки: `undefined` — пусто, `NaN` — нечитаемо (текст, дата, «да/нет»). */
export function cellNumber(v: unknown): number | undefined {
  if (v === null || v === undefined) return undefined;
  if (typeof v === "number") return Number.isFinite(v) ? v : Number.NaN;
  if (typeof v !== "string") return Number.NaN;
  const s = v.trim();
  if (s === "") return undefined;
  if (PLAIN.test(s)) return Number(s.replace(",", "."));
  if (GROUPED.test(s)) return Number(s.replace(/[ \u00a0\u202f]/g, "").replace(",", "."));
  return Number.NaN;
}

/** Текст ячейки без краевых пробелов; пусто — "". */
export function cellText(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v).trim();
}

/** Имя для сопоставления: без регистра и лишних пробелов («  Хлеб » ≡ «хлеб»). */
export function matchKey(v: unknown): string {
  return cellText(v).toLowerCase().replace(/\s+/g, " ");
}

export type SeriesResult = { values: string[] } | { error: string };

/**
 * Ряд по месяцам длины `n` (лишнее отрезается): пусто → «0», нечитаемое — ошибка с
 * номером месяца, и ряд целиком не применяется.
 */
export function cellSeries(cells: unknown[], n: number): SeriesResult {
  const values: string[] = [];
  for (let i = 0; i < n; i++) {
    const x = cellNumber(cells[i]);
    if (x === undefined) {
      values.push("0");
      continue;
    }
    if (Number.isNaN(x)) return { error: `М${i + 1}: «${cellText(cells[i])}» — не число` };
    values.push(String(x));
  }
  return { values };
}
