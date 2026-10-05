// Факт ДДС из Excel и 1С (пакет L, L7). Факт кэш-фло вводился руками по ячейкам, а у
// предприятия он уже есть — выгрузкой «Анализ движения денежных средств» из 1С или
// таблицей бухгалтера: статьи по строкам, месяцы по колонкам.
//
// Правила (все — в отчёте импорта, а не в догадках пользователя):
//
// * **месяцы — по заголовку**: «Январь 2026», «янв. 26», «01.2026», дата-ячейка или «М1»
//   шаблона продукта; колонка, которую не прочесть как месяц горизонта («Итого», месяц
//   до старта или после конца), не загружается и названа;
// * **статья → строка кэш-фло**: сперва сохранённое сопоставление (модель помнит прошлый
//   импорт), потом точное название строки, потом подсказка по словам («оплата от
//   покупателей» → C1, «налоги» → C12 …). Подсказка — предложение: человек видит её до
//   загрузки и может поменять; выбранное сохраняется в модели;
// * **несопоставленное не загружается** и названо; итоги и остатки («Итого», «Остаток на
//   начало») пропускаются — они не поток;
// * **нечитаемая ячейка не становится нулём** (`xlsxCells`): месяц этой строки кэш-фло
//   из файла не обновляется (остаётся прежний факт или план), и это названо;
// * **знак выплат** — по статье: все суммы статьи-выплаты ≤ 0 — выгрузка со знаком
//   («минус — выплата»), и они берутся по модулю; все ≥ 0 — как есть; и плюсы, и минусы —
//   не понять, что из них выплата, статья не загружается и названа;
// * несколько статей на одну строку **складываются** («Аренда» + «Связь» → общие
//   издержки); месяцы, которых в файле нет, сохраняют прежний факт.
//
// К расчётному ядру отношения не имеет: правит модель, как ручной ввод на вкладке «Факт».
import type { Actualization } from "./api/model";
import { cellNumber, cellText, matchKey } from "./xlsxCells";

/** Строка кэш-фло, куда можно положить факт: код, подпись, поступление ли это. */
export interface FactLine {
  code: string;
  label: string;
  inflow: boolean;
}

/**
 * Листовые потоки кэш-фло — подписи те же, что в отчёте. Остаток денег на начало (C28)
 * сюда не входит: это не поток, а следствие потоков.
 */
export const FACT_LINES: FactLine[] = [
  { code: "C1", label: "Поступления от продаж", inflow: true },
  { code: "C2", label: "Затраты на материалы и комплектующие", inflow: false },
  { code: "C3", label: "Затраты на сдельную заработную плату", inflow: false },
  { code: "C5", label: "Общие издержки", inflow: false },
  { code: "C6", label: "Затраты на персонал", inflow: false },
  { code: "C8", label: "Вложения в краткосрочные ценные бумаги", inflow: false },
  { code: "C9", label: "Доходы по краткосрочным ценным бумагам", inflow: true },
  { code: "C10", label: "Другие поступления", inflow: true },
  { code: "C11", label: "Другие выплаты", inflow: false },
  { code: "C12", label: "Налоги", inflow: false },
  { code: "C14", label: "Затраты на приобретение активов", inflow: false },
  { code: "C15", label: "Другие издержки подготовительного периода", inflow: false },
  { code: "C16", label: "Поступления от реализации активов", inflow: true },
  { code: "C21", label: "Собственный (акционерный) капитал", inflow: true },
  { code: "C22", label: "Займы", inflow: true },
  { code: "C23", label: "Выплаты в погашение займов", inflow: false },
  { code: "C24", label: "Выплаты процентов по займам", inflow: false },
  { code: "C25", label: "Лизинговые платежи", inflow: false },
  { code: "C26", label: "Выплаты дивидендов", inflow: false },
];

const BY_CODE = new Map(FACT_LINES.map((l) => [l.code, l]));

/**
 * Подсказки по словам статьи — от частного к общему: «проценты по кредитам» раньше
 * «кредита», «сдельная оплата» раньше «оплаты труда». Это предложение, а не решение:
 * человек видит его до загрузки.
 */
const HINTS: [RegExp, string][] = [
  [/процент/, "C24"],
  [/лизинг/, "C25"],
  [/дивиденд/, "C26"],
  [/(погашени|возврат).*(кредит|займ|заём)/, "C23"],
  [/(получени|поступлени).*(кредит|займ|заём)|(кредит|займ|заём).*получ/, "C22"],
  [/(взнос|вклад).*(капитал|учредител|участник)|уставн/, "C21"],
  [/(продаж|реализац).*(основн|оборудован|имуществ|актив)/, "C16"],
  [/налог|ндс|ндфл|взнос|сбор|пени|штраф/, "C12"],
  [/сдельн/, "C3"],
  [/зарплат|заработн|оплата труда|персонал|оклад|аванс сотрудник|отпускн/, "C6"],
  [/(приобретени|покупк|поставк).*(основн|оборудован|техник|транспорт)|капитальн|строительств/, "C14"],
  [/покупател|выручк|реализац|оплата от|поступлени.*(продаж|клиент)/, "C1"],
  [/поставщик|материал|сырь|комплектующ|товар/, "C2"],
  [/аренд|коммунал|связь|интернет|реклам|маркетинг|услуг|хоз|офис|транспорт|топлив|бензин|банковск|комисси|страхован|ремонт|обслуживан/, "C5"],
  [/прочие поступлени|прочие доход/, "C10"],
  [/прочие (выплат|расход|списани)/, "C11"],
];

/** Итоги и остатки — не поток; пропускаются и называются. */
const NOT_A_FLOW = /^(итого|всего|остаток|сальдо|оборот)|остаток на (начало|конец)/;

/** Ключ статьи для сохранённого сопоставления — тот же, что у других импортов. */
export const articleKey = matchKey;

export type Source = "saved" | "exact" | "hint" | "none";

export interface Suggestion {
  /** Код строки кэш-фло; "" — не загружать. */
  code: string;
  source: Source;
}

/** Куда положить статью: сохранённое → точное название → подсказка → никуда. */
export function suggest(label: string, mapping: Record<string, string> = {}): Suggestion {
  const key = articleKey(label);
  if (key in mapping) return { code: mapping[key], source: "saved" };
  const exact = FACT_LINES.find((l) => matchKey(l.label) === key || l.code.toLowerCase() === key);
  if (exact) return { code: exact.code, source: "exact" };
  for (const [pattern, code] of HINTS) if (pattern.test(key)) return { code, source: "hint" };
  return { code: "", source: "none" };
}

// --- Месяцы в заголовке ---

const MONTHS: [RegExp, number][] = [
  [/^янв/, 1], [/^фев/, 2], [/^мар/, 3], [/^апр/, 4], [/^ма[йя]/, 5], [/^июн/, 6],
  [/^июл/, 7], [/^авг/, 8], [/^сен/, 9], [/^окт/, 10], [/^ноя/, 11], [/^дек/, 12],
];

/** Год и месяц из заголовка колонки; `null` — это не месяц. */
export function monthOf(cell: unknown): { year: number; month: number } | { index: number } | null {
  if (cell instanceof Date && !Number.isNaN(cell.getTime())) {
    return { year: cell.getFullYear(), month: cell.getMonth() + 1 };
  }
  const text = cellText(cell).toLowerCase().replace(/\s+г\.?$/, "").trim();
  if (!text) return null;
  const m = /^м\s*(\d{1,3})$/.exec(text);                       // «М1» шаблона продукта
  if (m) return { index: Number(m[1]) - 1 };
  const numeric = /^(\d{1,2})[./-](\d{4}|\d{2})$/.exec(text);     // «01.2026», «1/26»
  if (numeric) {
    const month = Number(numeric[1]);
    const year = Number(numeric[2].length === 2 ? "20" + numeric[2] : numeric[2]);
    return month >= 1 && month <= 12 ? { year, month } : null;
  }
  const iso = /^(\d{4})-(\d{1,2})/.exec(text);                   // «2026-01»
  if (iso) {
    const month = Number(iso[2]);
    return month >= 1 && month <= 12 ? { year: Number(iso[1]), month } : null;
  }
  const words = /^([а-яё]+)\.?\s*(\d{4}|\d{2})$/.exec(text);     // «январь 2026», «янв. 26»
  if (words) {
    const hit = MONTHS.find(([re]) => re.test(words[1]));
    if (!hit) return null;
    const year = Number(words[2].length === 2 ? "20" + words[2] : words[2]);
    return { year, month: hit[1] };
  }
  return null;
}

/** Индекс месяца горизонта для заголовка; `null` — не месяц или вне горизонта. */
function horizonIndex(cell: unknown, start: string, n: number): number | null {
  const parsed = monthOf(cell);
  if (!parsed) return null;
  let index: number;
  if ("index" in parsed) {
    index = parsed.index;
  } else {
    const [y, mo] = start.split("-").map(Number);
    index = (parsed.year - y) * 12 + (parsed.month - mo);
  }
  return index >= 0 && index < n ? index : null;
}

// --- Разбор листа ---

export interface Article {
  label: string;
  /** Значение по месяцу горизонта: число, `undefined` — пусто, `NaN` — нечитаемо. */
  values: Map<number, number>;
  unreadable: number[];
}

export interface ParsedSheet {
  articles: Article[];
  /** Месяцы горизонта, найденные в заголовке (по возрастанию). */
  months: number[];
  /** Колонки заголовка, которые не загружаются, — с причиной. */
  skippedColumns: string[];
  /** Строки, которые не загружаются (итоги, остатки), — подписями. */
  skippedRows: string[];
  /** Почему файл не разобран вовсе; пусто — разобран. */
  error: string;
}

/** Разобрать лист «статья × месяц». `start` — дата старта модели, `n` — горизонт. */
export function parseCashflowRows(rows: unknown[][], start: string, n: number): ParsedSheet {
  const out: ParsedSheet = { articles: [], months: [], skippedColumns: [], skippedRows: [], error: "" };
  // Заголовок — первая строка (из первых двадцати), где есть хотя бы одна колонка-месяц.
  let header = -1;
  for (let r = 0; r < Math.min(rows.length, 20); r++) {
    if ((rows[r] ?? []).some((c) => monthOf(c) !== null)) { header = r; break; }
  }
  if (header < 0) {
    out.error = "Не нашлось строки заголовка с месяцами («Январь 2026», «01.2026» или «М1» " +
      "шаблона). Статьи — по строкам, месяцы — по колонкам.";
    return out;
  }
  const columns = new Map<number, number>();               // колонка → месяц горизонта
  const head = rows[header];
  head.forEach((cell, col) => {
    if (col === 0) return;
    const text = cellText(cell instanceof Date ? cell.toISOString().slice(0, 7) : cell);
    if (!text) return;
    const index = horizonIndex(cell, start, n);
    if (index === null) {
      out.skippedColumns.push(monthOf(cell) ? `«${text}» — вне горизонта модели` : `«${text}»`);
    } else {
      columns.set(col, index);
    }
  });
  out.months = [...new Set(columns.values())].sort((a, b) => a - b);
  // Числа под колонкой без месяца в заголовке (в выгрузках 1С бывают подколонки
  // «Приход» / «Расход» под одним месяцем) молча пропасть не должны — колонка названа.
  const orphans = new Set<number>();
  for (const row of rows.slice(header + 1)) {
    (row ?? []).forEach((cell, col) => {
      if (col > 0 && !columns.has(col) && !cellText(head[col]) && cellNumber(cell) !== undefined) {
        orphans.add(col);
      }
    });
  }
  for (const col of [...orphans].sort((a, b) => a - b)) {
    out.skippedColumns.push(`колонка № ${col + 1} без месяца в заголовке — числа в ней не ` +
      "загружены; если это подколонки «Приход» и «Расход», сведите их в одну колонку на месяц");
  }
  for (const row of rows.slice(header + 1)) {
    const label = cellText(row?.[0]);
    if (!label) continue;
    const values = new Map<number, number>();
    const unreadable: number[] = [];
    let any = false;
    for (const [col, index] of columns) {
      const x = cellNumber(row[col]);
      if (x === undefined) continue;
      any = true;
      if (Number.isNaN(x)) unreadable.push(index);
      else values.set(index, (values.get(index) ?? 0) + x);
    }
    if (!any) continue;                                     // заголовок группы без чисел
    if (NOT_A_FLOW.test(matchKey(label))) { out.skippedRows.push(label); continue; }
    out.articles.push({ label, values, unreadable });
  }
  return out;
}

// --- Применение ---

export interface CashflowReport {
  /** Загружено: статья → строка, месяцев. */
  loaded: { label: string; code: string; months: number }[];
  /** Не загружено — с причиной. */
  ignored: { label: string; reason: string }[];
  /** Месяцы строк кэш-фло, оставшиеся без факта из-за нечитаемых ячеек. */
  unreadable: string[];
  /** Пояснения о знаке выплат. */
  signs: string[];
  /** Новый «факт до месяца» (индекс), если сдвинулся. */
  actualUntil: number;
}

/**
 * Наложить разобранный лист на факт модели. `choice` — решение человека по статьям
 * (ключ — `articleKey`): код строки или "" — не загружать.
 */
export function applyCashflow(actualization: Actualization, sheet: ParsedSheet,
                              choice: Record<string, string>, n: number):
  { actualization: Actualization; report: CashflowReport } {
  const report: CashflowReport = { loaded: [], ignored: [], unreadable: [], signs: [],
                                   actualUntil: actualization.actual_until };
  const sums = new Map<string, Map<number, number>>();
  const broken = new Map<string, Set<number>>();
  const mapping = { ...(actualization.mapping ?? {}) };
  for (const article of sheet.articles) {
    const key = articleKey(article.label);
    const code = choice[key] ?? "";
    mapping[key] = code;
    if (!code) {
      report.ignored.push({ label: article.label, reason: "не сопоставлена со строкой кэш-фло" });
      continue;
    }
    const line = BY_CODE.get(code);
    if (!line) {
      report.ignored.push({ label: article.label, reason: `строки ${code} нет среди потоков` });
      continue;
    }
    const numbers = [...article.values.values()];
    let sign = 1;
    if (line.inflow && numbers.length && numbers.every((v) => v < 0)) {
      report.signs.push(`«${article.label}»: поступления только со знаком минус — проверьте, ` +
        "та ли это строка кэш-фло.");
    }
    if (!line.inflow) {
      const negative = numbers.some((v) => v < 0);
      const positive = numbers.some((v) => v > 0);
      if (negative && positive) {
        report.ignored.push({ label: article.label, reason: "и плюсы, и минусы — не понять, " +
          "что из них выплата; поправьте знаки в файле" });
        continue;
      }
      if (negative) {
        sign = -1;
        report.signs.push(`«${article.label}»: суммы со знаком минус приняты как выплаты.`);
      }
    }
    const target = sums.get(code) ?? new Map<number, number>();
    for (const [index, value] of article.values) target.set(index, (target.get(index) ?? 0) + sign * value);
    sums.set(code, target);
    if (article.unreadable.length) {
      const set = broken.get(code) ?? new Set<number>();
      article.unreadable.forEach((i) => set.add(i));
      broken.set(code, set);
    }
    report.loaded.push({ label: article.label, code, months: article.values.size });
  }

  const actuals: Record<string, (string | null)[]> = { ...actualization.actuals };
  let last = actualization.actual_until;
  for (const [code, byMonth] of sums) {
    const series = Array.from({ length: n }, (_, t) => actuals[code]?.[t] ?? null);
    for (const [index, value] of byMonth) {
      // Месяц, где хоть одна ячейка статей этой строки нечитаема, остаётся без факта:
      // сумма без неё была бы неправдой.
      if (broken.get(code)?.has(index)) continue;
      series[index] = String(Math.round(value * 100) / 100);
      last = Math.max(last, index);
    }
    actuals[code] = series;
  }
  for (const [code, months] of broken) {
    const line = BY_CODE.get(code);
    for (const index of [...months].sort((a, b) => a - b)) {
      report.unreadable.push(`${line?.label ?? code}, М${index + 1}: в файле нечитаемая ` +
        "ячейка — месяц из файла не обновлён");
    }
  }
  report.actualUntil = last;
  return { actualization: { actual_until: last, actuals, mapping }, report };
}

// --- Шаблон и файл ---

/** Подписи месяцев горизонта: «Янв 2026» … — тот же разбор читает их обратно. */
export function monthLabels(start: string, n: number): string[] {
  const names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август",
                 "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
  const [y, m] = start.split("-").map(Number);
  return Array.from({ length: n }, (_, t) => {
    const k = m - 1 + t;
    return `${names[k % 12]} ${y + Math.floor(k / 12)}`;
  });
}

type XCell = { value: string; type: StringConstructor; fontWeight?: "bold" };

/** Шаблон: статьи — строки кэш-фло продукта, месяцы — горизонт модели. */
export function buildCashflowTemplate(start: string, n: number): XCell[][] {
  const head: XCell[] = [{ value: "Статья ДДС", type: String, fontWeight: "bold" },
    ...monthLabels(start, n).map((v) => ({ value: v, type: String, fontWeight: "bold" as const }))];
  return [head, ...FACT_LINES.map((l) => [{ value: l.label, type: String }])];
}

export async function downloadCashflowTemplate(start: string, n: number,
                                               fileName = "fact-cashflow.xlsx"): Promise<void> {
  const writeXlsxFile = (await import("write-excel-file/browser")).default;
  const columns = [{ width: 40 }, ...Array.from({ length: n }, () => ({ width: 14 }))];
  await writeXlsxFile([{ data: buildCashflowTemplate(start, n), sheet: "ДДС", columns }])
    .toFile(fileName);
}

/** Прочитать первый лист книги (выгрузки 1С — одним листом). */
export async function readCashflowXlsx(file: Blob): Promise<unknown[][]> {
  const readXlsxFile = (await import("read-excel-file")).default;
  return (await readXlsxFile(file as File)) as unknown[][];
}
