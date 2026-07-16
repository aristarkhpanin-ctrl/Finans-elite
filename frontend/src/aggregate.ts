import type { StatementOut } from "./api/calc";

/**
 * Агрегация отчётов по периодам — слой отображения (пакет №6, G0; решения Q1–Q2
 * в docs/AGGREGATION-DRILLDOWN-DECOMPOSITION.md). Зеркало правил `app/docgen.py`:
 * потоки — суммы за период; баланс — конец периода; C28/P2 — начало; C29/P7 — конец;
 * P3 = P2 + ΣP1 (тождества помесячного отчёта сохраняются). Ядро не трогаем.
 */

export type Period = "month" | "quarter" | "year";

/** Вид отчёта для правил свёртки: баланс — остатки, остальные — потоки (+ исключения). */
export type StatementKind = "flow" | "balance";

const CHUNK: Record<Exclude<Period, "month">, number> = { quarter: 3, year: 12 };

/** Строки-остатки внутри «потоковых» отчётов: начало периода / конец периода. */
const FIRST_OF_PERIOD = new Set(["C28", "P2"]);
const LAST_OF_PERIOD = new Set(["C29", "P7"]);

/** Дефолтный период по горизонту (Q1): до 2 лет — месяц, до 6 — квартал, дальше — год. */
export function defaultPeriod(n: number): Period {
  if (n <= 24) return "month";
  if (n <= 72) return "quarter";
  return "year";
}

/** Полуинтервалы [a, b) месяцев по периодам; последний период может быть неполным. */
export function periodChunks(n: number, period: Period): [number, number][] {
  if (period === "month") return Array.from({ length: n }, (_, i) => [i, i + 1]);
  const size = CHUNK[period];
  const out: [number, number][] = [];
  for (let a = 0; a < n; a += size) out.push([a, Math.min(a + size, n)]);
  return out;
}

/** Метки колонок: М1… / К1… / Год 1… (нумерация от старта проекта, как в DOCX). */
export function periodLabels(n: number, period: Period): string[] {
  const count = periodChunks(n, period).length;
  const prefix = period === "month" ? "М" : period === "quarter" ? "К" : "Год ";
  return Array.from({ length: count }, (_, i) => `${prefix}${i + 1}`);
}

/** Денежная строка API («1234.56») → целые копейки. Пустое/нечисловое → 0. */
function toCents(v: string): number {
  const x = Number(v);
  return Number.isFinite(x) ? Math.round(x * 100) : 0;
}

const fromCents = (c: number): string => String(c / 100);

/** Свернуть один ряд значений по правилу: sum | first | last. */
function foldSeries(values: string[], chunks: [number, number][],
                    rule: "sum" | "first" | "last"): string[] {
  return chunks.map(([a, b]) => {
    if (rule === "first") return values[a];
    if (rule === "last") return values[b - 1];
    let acc = 0;
    for (let t = a; t < b; t++) acc += toCents(values[t]);
    return fromCents(acc);
  });
}

function ruleFor(code: string, kind: StatementKind): "sum" | "first" | "last" {
  if (kind === "balance" || LAST_OF_PERIOD.has(code)) return "last";
  if (FIRST_OF_PERIOD.has(code)) return "first";
  return "sum";
}

/**
 * Свернуть отчёт по периодам. `month` возвращает исходный отчёт (без копий).
 * P3 («прибыль к распределению») выводится заново как P2 + P1 периода.
 */
export function aggregateStatement(stmt: StatementOut, kind: StatementKind,
                                   n: number, period: Period): StatementOut {
  if (period === "month") return stmt;
  const chunks = periodChunks(n, period);
  const byCode = new Map<string, string[]>();
  const lines = stmt.lines.map((l) => {
    const values = foldSeries(l.values, chunks, ruleFor(l.code, kind));
    byCode.set(l.code, values);
    return { ...l, values };
  });
  const p1 = byCode.get("P1");
  const p2 = byCode.get("P2");
  if (p1 && p2) {
    const p3 = p1.map((v, i) => fromCents(toCents(v) + toCents(p2[i])));
    for (const l of lines) if (l.code === "P3") l.values = p3;
  }
  return { ...stmt, lines };
}

/** Свернуть произвольный потоковый ряд (детализация строк, G3). */
export function aggregateFlowSeries(values: string[], n: number, period: Period): string[] {
  if (period === "month") return values;
  return foldSeries(values, periodChunks(n, period), "sum");
}
