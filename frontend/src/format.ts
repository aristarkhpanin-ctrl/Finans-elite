/** Форматирование денежных сумм (строка Decimal → ru-RU, без дробной части). */
export function money(s: string | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const x = Number(s);
  if (!Number.isFinite(x)) return "—";
  return x.toLocaleString("ru-RU", { maximumFractionDigits: 0 });
}

/** Форматирование коэффициента (до 3 знаков; null → «—»). */
export function ratio(s: string | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const x = Number(s);
  if (!Number.isFinite(x)) return "—";
  return x.toLocaleString("ru-RU", { maximumFractionDigits: 3 });
}

/** Процент (доля → %). */
export function percent(s: string | null | undefined, digits = 1): string {
  if (s === null || s === undefined) return "—";
  const x = Number(s);
  if (!Number.isFinite(x)) return "—";
  return (x * 100).toLocaleString("ru-RU", { maximumFractionDigits: digits }) + "%";
}
