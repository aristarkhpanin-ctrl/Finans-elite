// Чистая логика MonthlyGrid — без React, покрыта юнит-тестами (monthlyGrid.logic.test.ts).
// Разбор вставки из Excel и парсинг/форматирование чисел вынесены сюда, чтобы
// ошибки в них (искажение введённых пользователем сумм) ловились тестами.

export const NBSP = " ";

/** Строка → число: пробелы (в т.ч. NBSP) убираются, запятая → точка; мусор → 0. */
export const num = (v: string | undefined): number => {
  if (!v) return 0;
  const x = Number(String(v).replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
};

/** Нормализация вставленного значения: пробелы прочь, запятая → точка. */
export const norm = (x: string): string => x.trim().replace(/\s/g, "").replace(",", ".");

/** Целое с группировкой тысяч NBSP и типографским минусом: -1234567 → «−1 234 567». */
export const fmtInt = (n: number): string => {
  const r = Math.round(n);
  const s = String(Math.abs(r)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return (r < 0 ? "−" : "") + s;
};

/** Крупные суммы в чипе — «12,40 млн». */
export const fmtAgg = (n: number): string =>
  Math.abs(n) >= 1e6 ? (n / 1e6).toFixed(2).replace(".", ",") + NBSP + "млн" : fmtInt(n);

/** Русская форма множественного числа: plural(2, «значение», «значения», «значений»). */
export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

/** Разбить вставленный из Excel/таблиц текст на значения (табы, «;», переводы строк). */
export function splitPasted(text: string): string[] {
  return text.split(/[\t;\n\r]+/).map((p) => p.trim()).filter(Boolean);
}

/**
 * Применить вставку из буфера к ряду длины `n`, начиная с колонки `i`.
 * Возвращает новый массив значений и число заполненных ячеек, либо `null`,
 * если во вставке ≤1 значения (тогда это обычная вставка одиночного значения).
 */
export function applyPaste(
  current: string[],
  i: number,
  text: string,
  n: number,
): { values: string[]; filled: number } | null {
  const parts = splitPasted(text);
  if (parts.length <= 1) return null;
  const values = Array.from({ length: n }, (_, k) =>
    k >= i && parts[k - i] !== undefined ? norm(parts[k - i]) : (current[k] ?? ""),
  );
  return { values, filled: Math.min(parts.length, n - i) };
}
