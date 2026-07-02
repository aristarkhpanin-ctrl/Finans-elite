/**
 * Форматирование чисел (Р7) и конвертация процентов (Р10).
 *
 * Все новые форматтеры повторяют поведение макетов Modal:
 * - fmtTable  — «Этап 13»: тысячи через NBSP, отрицательные «(1 234)», ноль/null «—»;
 * - fmtMoney  — «Этап 15»: «12 480 000 ₽», минус — типографский «−»;
 * - fmtAxis   — «Этап 15»: короткие подписи осей «8,4м» / «320к»;
 * - fmtMillions — «Этап 12»: «−4,2 млн ₽» (опционально с «+»);
 * - fmtRatio  — «Этап 14»: запятая-десятичная, единица измерения отдельным чипом.
 */

const NBSP = " ";
const MINUS = "−";

function toNum(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const x = typeof v === "number" ? v : Number(String(v).replace(",", "."));
  return Number.isFinite(x) ? x : null;
}

/** Группировка тысяч неразрывным пробелом: 1234567 → «1 234 567». */
function groupNbsp(abs: number): string {
  return String(abs).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
}

// ───────────────────────── Легаси-форматтеры (до завершения миграции) ─────────

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

// ───────────────────────── Р7. Новые форматтеры (макеты Modal) ────────────────

export type TableCellKind = "pos" | "neg" | "zero";

export interface TableCell {
  text: string;
  kind: TableCellKind;
}

/**
 * Ячейка финансовой таблицы («Этап 13»): 0/null → «—» (kind zero),
 * отрицательные — «(1 234)» (kind neg), положительные — «1 234» (kind pos).
 */
export function fmtTable(v: number | string | null | undefined): TableCell {
  const x = toNum(v);
  if (x === null || Math.round(x) === 0) return { text: "—", kind: "zero" };
  const neg = x < 0;
  const s = groupNbsp(Math.abs(Math.round(x)));
  return { text: neg ? `(${s})` : s, kind: neg ? "neg" : "pos" };
}

/** Деньги («Этап 15»): «12 480 000 ₽», отрицательные — «−12 480 000 ₽»; null → «—». */
export function fmtMoney(v: number | string | null | undefined): string {
  const x = toNum(v);
  if (x === null) return "—";
  const neg = x < 0;
  return (neg ? MINUS : "") + groupNbsp(Math.abs(Math.round(x))) + NBSP + "₽";
}

/** Короткая подпись оси («Этап 15»): ≥1 млн → «8,4м»/«12м», ≥1 тыс → «320к», иначе целое. */
export function fmtAxis(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e6) return (v / 1e6).toFixed(a < 1e7 ? 1 : 0).replace(".", ",") + "м";
  if (a >= 1e3) return String(Math.round(v / 1e3)) + "к";
  return String(Math.round(v));
}

/**
 * Миллионы («Этап 12»): «−4,2 млн ₽»; с opts.sign — «+18,4 млн ₽».
 * null → «—».
 */
export function fmtMillions(
  v: number | string | null | undefined,
  opts: { sign?: boolean; digits?: number } = {},
): string {
  const x = toNum(v);
  if (x === null) return "—";
  const digits = opts.digits ?? 1;
  const abs = (Math.abs(x) / 1e6).toFixed(digits).replace(".", ",");
  const sign = x < 0 ? MINUS : opts.sign && x > 0 ? "+" : "";
  return sign + abs + NBSP + "млн" + NBSP + "₽";
}

/**
 * Коэффициент («Этап 14»): запятая-десятичная, фиксированное число знаков,
 * отрицательные — с «−»; null/NaN → «—». Единица (×/%/дн./₽) выводится отдельно.
 */
export function fmtRatio(v: number | string | null | undefined, digits = 2): string {
  const x = toNum(v);
  if (x === null) return "—";
  const s = Math.abs(x).toFixed(digits).replace(".", ",");
  return (x < 0 ? MINUS : "") + s;
}

// ───────────────────────── Р10. Конвертация процентов ─────────────────────────

/**
 * Точный сдвиг десятичной точки в строке Decimal (без плавающей точки).
 * Возвращает каноническую строку с точкой («20.5», «0.205») или null,
 * если вход не является простым десятичным числом.
 */
function shiftDecimalString(raw: string, shift: number): string | null {
  const m = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(raw.trim().replace(",", "."));
  if (!m) return null;
  const sign = m[1] === "-" ? "-" : "";
  let digits = m[2] + (m[3] ?? "");
  let point = m[2].length + shift;
  if (point <= 0) {
    digits = "0".repeat(1 - point) + digits;
    point = 1;
  }
  if (point > digits.length) digits += "0".repeat(point - digits.length);
  const int = digits.slice(0, point).replace(/^0+(?=\d)/, "");
  const frac = digits.slice(point).replace(/0+$/, "");
  if (/^0*$/.test(int) && frac === "") return "0";
  return sign + int + (frac ? "." + frac : "");
}

/**
 * Доля → проценты для поля ввода: «0.205» → «20.5», «0.2» → «20».
 * Модель хранит доли (0–1), UI показывает проценты. Пустое/некорректное → «».
 */
export function fracToPct(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  return shiftDecimalString(String(v), 2) ?? "";
}

/**
 * Проценты из поля ввода → доля для модели: «20.5»/«20,5» → «0.205».
 * Пустое/некорректное → «».
 */
export function pctToFrac(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  return shiftDecimalString(String(v), -2) ?? "";
}
