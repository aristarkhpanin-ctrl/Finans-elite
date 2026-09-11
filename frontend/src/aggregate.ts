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

/** Денежная строка API («1234.56») → число. Пустое/нечисловое → 0. */
function toNumber(v: string): number {
  const x = Number(v);
  return Number.isFinite(x) ? x : 0;
}

const fromCents = (c: number): string => String(c / 100);

/**
 * Свернуть один ряд значений по правилу: sum | first | last.
 *
 * Суммирование идёт **в полной точности**, а к копейкам приводится один раз — в конце.
 * Раньше каждый месяц округлялся до копеек до сложения, и годовое число расходилось с тем,
 * что печатает DOCX-генератор (он складывает Decimal и округляет однажды): на реальном
 * проекте расхождение доходило до 2 копеек. Ряды приходят с полной точностью Decimal,
 * поэтому терять её на промежуточном шаге нельзя — округление живёт на границе вывода.
 */
function foldSeries(values: string[], chunks: [number, number][],
                    rule: "sum" | "first" | "last"): string[] {
  return chunks.map(([a, b]) => {
    if (rule === "first") return values[a];
    if (rule === "last") return values[b - 1];
    let acc = 0;
    for (let t = a; t < b; t++) acc += toNumber(values[t]);
    return fromCents(Math.round(acc * 100));
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
  const raw = new Map(stmt.lines.map((l) => [l.code, l.values]));
  const lines = stmt.lines.map((l) => (
    { ...l, values: foldSeries(l.values, chunks, ruleFor(l.code, kind)) }
  ));
  const rawP1 = raw.get("P1");
  const rawP2 = raw.get("P2");
  if (rawP1 && rawP2) {
    // Тождество выводится из **исходных** рядов, а не из уже свёрнутых: P2 на начало
    // периода плюс сумма P1 за период, округление — один раз. Складывать округлённые
    // слагаемые значило бы копить копейку, которой нет в документе.
    const p3 = chunks.map(([a, b]) => {
      let acc = toNumber(rawP2[a]);
      for (let t = a; t < b; t++) acc += toNumber(rawP1[t]);
      return fromCents(Math.round(acc * 100));
    });
    for (const l of lines) if (l.code === "P3") l.values = p3;
  }
  return { ...stmt, lines };
}

/** Свернуть произвольный потоковый ряд (детализация строк, G3). */
export function aggregateFlowSeries(values: string[], n: number, period: Period): string[] {
  if (period === "month") return values;
  return foldSeries(values, periodChunks(n, period), "sum");
}
