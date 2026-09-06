// Выгрузка результатов анализа (Финанс-Аудит): вердикт, находки, качество прибыли,
// обязательства, оценка, риски, план-факт — и следом аналитическая форма, тренды,
// коэффициенты, диагностика, свои показатели. По листу на раздел.
//
// Здесь только сборка листов из готового ответа `/analyze` — ничего не пересчитывается,
// поэтому файл не может разойтись с экраном. Ключевое соглашение аналитики сохраняется и
// в выгрузке: **неопределённый показатель (нулевая база) остаётся пустой ячейкой**, а не
// нулём — ноль в Excel читался бы как посчитанное значение. То же и с флагом без денежной
// меры: ячейка пуста, а словами сказано, что меры нет.
//
// Порядок листов — тот же, что в документе (SPEC, Приложение У.2): сначала вывод и
// находки, потом числа, на которых они стоят. Ради таблицы файл и просят: до этого
// выгрузка несла одно финансовое состояние, а находки и оценка оставались на экране.
import type { AuditAnalysis, AuditLineOut } from "./api/audit";
import { RATIO_GROUPS } from "./api/audit";

/** Ячейка XLSX для write-excel-file. */
type XCell = {
  value: string | number;
  type: StringConstructor | NumberConstructor;
  fontWeight?: "bold";
  format?: string;
} | null;

const MONEY = "#,##0.00";
const RATIO = "0.0000";
const PCT = "0.0%";

const head = (v: string): XCell => ({ value: v, type: String, fontWeight: "bold" });
const text = (v: string, bold?: boolean): XCell =>
  ({ value: v, type: String, ...(bold ? { fontWeight: "bold" as const } : {}) });
const num = (v: number, format: string, bold?: boolean): XCell =>
  ({ value: v, type: Number, format, ...(bold ? { fontWeight: "bold" as const } : {}) });

/** Строка-Decimal → число; пусто/невалидно → null («не определён»). */
const dec = (v: string | null | undefined): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const x = Number(String(v).replace(",", "."));
  return Number.isFinite(x) ? x : null;
};

/** Значение или пустая ячейка: «не определён» не подменяется нулём. */
const cell = (v: string | null | undefined, format: string, bold?: boolean): XCell => {
  const x = dec(v);
  return x === null ? null : num(x, format, bold);
};

/** Показатели-доли выводятся процентным форматом, денежные — денежным (как на экране). */
const PCT_RATIOS = /^(Рентабельность|Коэффициент автономии|Суммарные обязательства)/;
const MONEY_RATIOS = /^(Чистый оборотный капитал)/;
const ratioFormat = (name: string): string =>
  MONEY_RATIOS.test(name) ? MONEY : PCT_RATIOS.test(name) ? PCT : RATIO;

/** Подписи зон скоринга и статусов нормативов (зеркало вкладки «Диагностика»). */
const ZONE_LABEL: Record<string, string> = {
  safe: "устойчивость", grey: "неопределённость", distress: "высокий риск",
};
const STATUS_LABEL: Record<string, string> = {
  good: "норма", warn: "внимание", risk: "вне норматива",
};
const LIGHT_LABEL: Record<string, string> = {
  ok: "Устойчивое состояние", warning: "Есть зоны внимания", risk: "Признаки неустойчивости",
};

const headerRow = (first: string, periods: string[]): XCell[] =>
  [head(first), ...periods.map(head)];

/** Лист аналитической формы: баланс и ОПУ подряд, подытоги — жирным. */
export function formSheet(a: AuditAnalysis): XCell[][] {
  if (a.balance.length === 0 && a.income.length === 0) return [];
  const rows: XCell[][] = [];
  // Файл уходит из приложения, поэтому переоценка обязана быть видна и в нём: иначе
  // скорректированные числа разошлись бы по почте как учётная отчётность.
  if (a.revalued) {
    rows.push([head("Внимание: показатели рассчитаны с учётом переоценки статей — "
                    + "они отличаются от учётных данных.")]);
    rows.push([]);
  }
  rows.push(headerRow("Статья", a.periods));
  const section = (title: string, lines: AuditLineOut[]) => {
    rows.push([head(title), ...a.periods.map(() => head(""))]);
    for (const ln of lines) {
      rows.push([text(ln.label, ln.subtotal), ...ln.values.map((v) => cell(v, MONEY, ln.subtotal))]);
    }
  };
  section("АНАЛИТИЧЕСКИЙ БАЛАНС", a.balance);
  section("ОТЧЁТ О ФИНАНСОВЫХ РЕЗУЛЬТАТАХ", a.income);
  return rows;
}

/**
 * Лист трендов: на статью две строки — абсолютное изменение и темп к предыдущему периоду.
 * Первый период — база, у него изменения нет (пустая ячейка, не ноль).
 */
export function trendsSheet(a: AuditAnalysis): XCell[][] {
  if (a.horizontal.length === 0) return [];
  const rows: XCell[][] = [[head("Статья"), head("Показатель"), ...a.periods.map(head)]];
  for (const t of a.horizontal) {
    rows.push([text(t.label), text("Изменение"), ...t.delta.map((v) => cell(v, MONEY))]);
    rows.push([text(""), text("Темп прироста"), ...t.rate.map((v) => cell(v, PCT))]);
  }
  return rows;
}

/** Лист структуры: доля статьи в базе (баланс — от актива, ОПУ — от выручки). */
export function structureSheet(a: AuditAnalysis): XCell[][] {
  if (a.vertical.length === 0) return [];
  const rows: XCell[][] = [headerRow("Статья", a.periods)];
  for (const s of a.vertical) {
    rows.push([text(s.label), ...s.share.map((v) => cell(v, PCT))]);
  }
  return rows;
}

/** Лист коэффициентов: группы подряд, порядок — как на вкладке «Коэффициенты». */
export function ratiosSheet(a: AuditAnalysis): XCell[][] {
  const groups = RATIO_GROUPS.filter(([key]) => Object.keys(a.ratios[key] ?? {}).length > 0);
  if (groups.length === 0) return [];
  const rows: XCell[][] = [headerRow("Показатель", a.periods)];
  for (const [key, title] of groups) {
    const group = a.ratios[key];
    rows.push([head(title.toUpperCase()), ...a.periods.map(() => head(""))]);
    for (const [name, values] of Object.entries(group)) {
      const fmt = ratioFormat(name);
      rows.push([text(name), ...values.map((v) => cell(v, fmt))]);
    }
  }
  return rows;
}

/**
 * Лист диагностики: «светофор», скоринговые модели (значение + зона по периодам) и
 * оценки коэффициентов против нормативов. Пусто, если диагностика не считалась.
 */
export function diagnosticsSheet(a: AuditAnalysis): XCell[][] {
  const d = a.diagnostics;
  if (!d) return [];
  const rows: XCell[][] = [
    [head("Оценка"), text(LIGHT_LABEL[d.light] ?? d.light)],
    [head("Пояснение"), text(d.summary)],
    [],
  ];
  if (d.scores.length > 0) {
    rows.push([head("Модель"), head("Показатель"), ...a.periods.map(head)]);
    for (const s of d.scores) {
      rows.push([text(s.name), text("Значение"), ...s.values.map((v) => cell(v, RATIO))]);
      rows.push([text(""), text("Зона"), ...s.zones.map((z) => text(z ? ZONE_LABEL[z] ?? z : "—"))]);
      if (s.note) rows.push([text(""), text(s.note)]);
    }
    rows.push([]);
  }
  if (d.assessments.length > 0) {
    rows.push([head("Показатель"), head("Группа"), ...a.periods.map(head)]);
    for (const as of d.assessments) {
      rows.push([
        text(as.name),
        text(as.group),
        ...as.status.map((st) => text(st ? STATUS_LABEL[st] ?? st : "—")),
      ]);
    }
  }
  return rows;
}

/** Лист своих показателей (вкладка «Методики»); ошибка формулы выносится в колонку. */
export function metricsSheet(a: AuditAnalysis): XCell[][] {
  if (a.user_metrics.length === 0) return [];
  const rows: XCell[][] = [[head("Показатель"), ...a.periods.map(head), head("Ошибка")]];
  for (const u of a.user_metrics) {
    rows.push([text(u.name), ...u.values.map((v) => cell(v, RATIO)), text(u.error ?? "")]);
  }
  return rows;
}

/**
 * Лист вердикта: вывод, охват проверки, счётчики и список «что не посчитано».
 *
 * Охват стоит рядом с вердиктом: «проверено 18 из 28» меняет чтение вывода, а в конце
 * файла его прочтут уже после решения.
 */
export function verdictSheet(a: AuditAnalysis): XCell[][] {
  const s = a.summary;
  if (s.state !== "ready") return [];
  const p = a.procedures;
  const rows: XCell[][] = [
    [head("Вердикт"), text(s.headline)],
    [text("Пояснение"), text(s.detail)],
    [text("Флагов риска"), num(s.risk_flags, "0")],
    [text("Предупреждений"), num(s.warning_flags, "0")],
    [text("Оценённое влияние флагов"), cell(s.priced_total, MONEY)],
    [text("Флагов без денежной меры"), num(s.unpriced, "0")],
    [text("Охват проверки"), p.total ? text(`${p.closed} из ${p.total}`) : null],
    [text("Незакрытых процедур"), num(s.open_procedures, "0")],
  ];
  // Та же оговорка, что на экране, в документе и на бланке: сумма оценённых находок
  // и торг — разные величины. В таблице она особенно нужна: колонку с суммой легко
  // перенести в чужую модель как «скидку».
  rows.push([], [head("Оценённое влияние флагов — не скидка к цене.")]);
  if (s.not_computed.length > 0) {
    rows.push([], [head("Не посчитано")], ...s.not_computed.map((t) => [text(t)]));
  }
  return rows;
}

/** Лист реестра флагов. Флаг без денежной меры — пустая ячейка и слова, а не ноль. */
export function flagsSheet(a: AuditAnalysis): XCell[][] {
  const { flags, priced_total, unpriced } = a.flags;
  if (flags.length === 0) return [];
  const rows: XCell[][] = [[head("Находка"), head("Серьёзность"), head("Периоды"),
                            head("Оценка влияния"), head("Примечание")]];
  for (const f of flags) {
    rows.push([
      text(f.title),
      text(f.severity === "risk" ? "риск" : "внимание"),
      text(f.periods.map((i) => a.periods[i] ?? "").filter(Boolean).join(", ")),
      cell(f.impact, MONEY),
      text(f.impact === null ? "денежной меры нет" : f.detail),
    ]);
  }
  rows.push([text("Итого оценено", true), null, null, cell(priced_total, MONEY, true),
             text(unpriced > 0 ? `без меры ещё ${unpriced}` : "")]);
  return rows;
}

/** Лист качества прибыли: отчётный ряд, поправки, нормализованный ряд. */
export function earningsSheet(a: AuditAnalysis): XCell[][] {
  const e = a.earnings;
  if (e.reported.length === 0) return [];
  const rows: XCell[][] = [headerRow("Показатель", a.periods)];
  rows.push([text(`${e.base_code} по отчёту`), ...e.reported.map((v) => cell(v, MONEY))]);
  for (const adj of e.adjustments) {
    rows.push([text(`${adj.label} (${adj.kind_label})`),
               ...adj.amounts.map((v) => cell(v, MONEY))]);
  }
  rows.push([text(`${e.base_code} нормализованный`, true),
             ...e.normalized.map((v) => cell(v, MONEY, true))]);
  if (e.grade) {
    rows.push([], [text("Оценка качества прибыли"), text(e.grade)],
              [text("Отклонение от отчётного"), cell(e.deviation, PCT)]);
  }
  return rows;
}

/** Лист обязательств: реестр и сверка с балансом. Забалансовое — отдельной строкой. */
export function obligationsSheet(a: AuditAnalysis): XCell[][] {
  const o = a.obligations;
  const rows: XCell[][] = [
    [head("Показатель"), head("Сумма")],
    [text("Долг по реестру (в балансе)"), cell(o.balance_debt, MONEY)],
    [text("Долг по балансу отчётности"), cell(o.reported_debt, MONEY)],
    [text("Расхождение"), cell(o.discrepancy, MONEY)],
    // Забалансовое живёт отдельной строкой и никогда не входит в итог: сложение дало
    // бы величину, которой нет ни в одном отчёте.
    [text("Забалансовые (в сумму долга не входят)"), cell(o.off_balance, MONEY)],
    [text("Заложено активов"), cell(o.pledged_total, MONEY)],
    [text("Свободные активы"), cell(o.free_assets, MONEY)],
  ];
  if (o.rows.length === 0) return rows;
  rows.push([], [head("Кредитор"), head("Вид"), head("Сумма"), head("Срок"),
                 head("Ковенант")]);
  for (const r of o.rows) {
    rows.push([
      text(r.creditor + (r.contract ? ` · ${r.contract}` : "")),
      text(r.kind_label + (r.off_balance ? " (забаланс)" : "")),
      cell(r.amount, MONEY),
      text(r.maturity),
      text(r.covenant_note || r.covenant || ""),
    ]);
  }
  return rows;
}

/**
 * Лист оценки: мост EV → цена доли и условия расчёта.
 *
 * Лист выводится и тогда, когда оценка **не посчитана**: тогда на нём названы
 * препятствия. Пропустить его значило бы отдать читателю файл, из которого не видно,
 * что оценку вообще пытались посчитать.
 */
export function valuationSheet(a: AuditAnalysis): XCell[][] {
  const v = a.valuation;
  if (v.enterprise_value === null) {
    return [[head("Оценка не посчитана")], ...v.blockers.map((b) => [text(b)]),
            ...(v.not_computed.length
              ? [[], [head("Не посчитано")], ...v.not_computed.map((t) => [text(t)])]
              : [])];
  }
  const rows: XCell[][] = [[head("Статья"), head("Сумма")]];
  for (const b of v.bridge) {
    rows.push([text(b.label + (b.note ? ` — ${b.note}` : ""), b.kind === "total"),
               cell(b.amount, MONEY, b.kind === "total")]);
  }
  rows.push([],
            [text("Ставка дисконтирования"), cell(v.wacc, PCT)],
            [text("Рост в постпрогнозе"), cell(v.terminal_growth, PCT)],
            [text("Доля постпрогноза в EV"), cell(v.terminal_share, PCT)],
            [text("Подразумеваемый мультипликатор"), cell(v.implied_multiple, RATIO)],
            [text("Диапазон по чувствительности, от"), cell(v.equity_min, MONEY)],
            [text("Диапазон по чувствительности, до"), cell(v.equity_max, MONEY)],
            [text("Цена продавца"), cell(v.asking_price, MONEY)],
            [text("Дисконт к цене продавца"), cell(v.discount, PCT)]);
  if (v.warnings.length > 0) {
    rows.push([], ...v.warnings.map((w) => [text(w)]));
  }
  return rows;
}

/** Лист рисков: торнадо и Монте-Карло — с условием, при котором их читают. */
export function riskSheet(a: AuditAnalysis): XCell[][] {
  const r = a.risk;
  if (!r.available) {
    return r.blockers.length === 0 ? [] :
      [[head("Анализ рисков не считался")], ...r.blockers.map((b) => [text(b)])];
  }
  const rows: XCell[][] = [
    [text("Базовая цена доли"), cell(r.base_price, MONEY)],
    [text("Шаг смещения допущения"), cell(r.step, PCT)],
    [],
    [head("Допущение"), head("Ниже на шаг"), head("Выше на шаг"), head("Размах")],
  ];
  for (const t of r.tornado) {
    rows.push([text(t.label), cell(t.low_price, MONEY), cell(t.high_price, MONEY),
               cell(t.span, MONEY)]);
  }
  const mc = r.monte_carlo;
  if (mc) {
    rows.push([],
              [head("Монте-Карло"), head("Значение")],
              [text("Прогонов"), num(mc.iterations, "0")],
              [text("Оценка получена"), num(mc.valued, "0")],
              [text("Оценки не вышло"), num(mc.unvalued, "0")],
              [text("Медиана"), cell(mc.median, MONEY)],
              [text("10-й перцентиль"), cell(mc.p10, MONEY)],
              [text("90-й перцентиль"), cell(mc.p90, MONEY)],
              [text("Ниже запрошенной цены"), cell(mc.below_asking, PCT)],
              [],
              // Условие чтения блока, а не сноска: распределения задаёт аналитик.
              [head("Числа Монте-Карло ровно настолько хороши, насколько верны заданные "
                    + "распределения допущений.")]);
  }
  return rows;
}

/** Лист план-факта: только при введённом прогнозе продавца (иначе сравнивать нечего). */
export function planFactSheet(a: AuditAnalysis): XCell[][] {
  const pf = a.plan_fact;
  if (!pf.available) return [];
  const rows: XCell[][] = [[head("Строка"), head("План"), head("Факт"),
                            head("Отклонение"), head("Доля"), head("Оценка")]];
  for (const r of pf.rows) {
    rows.push([text(r.label), cell(r.plan, MONEY), cell(r.fact, MONEY),
               cell(r.delta, MONEY), cell(r.delta_share, PCT),
               text(VERDICT_LABEL[r.verdict] ?? r.verdict)]);
  }
  if (pf.flags.length > 0) {
    rows.push([],
              // Обе половины подписаны по источнику: «дисконт окупился» — сравнение
              // посчитанного с введённым, а не одного расчёта с другим.
              [text("Предсказанное влияние (посчитано платформой)"),
               cell(pf.predicted_total, MONEY)],
              [text("Фактические потери (введены аналитиком)"),
               cell(pf.realized_total, MONEY)]);
  }
  return rows;
}

const VERDICT_LABEL: Record<string, string> = {
  better: "лучше плана", worse: "хуже плана", on_plan: "в пределах порога",
};

/** Лист заключения: абзацы автотекста по строкам (для чтения и копирования). */
export function opinionSheet(a: AuditAnalysis): XCell[][] {
  const blocks = a.opinion.split("\n\n").filter((b) => b.trim() !== "");
  return blocks.length === 0 ? [] : [[head("Заключение")], ...blocks.map((b) => [text(b)])];
}

/** Лист → описание для write-excel-file; пустые разделы не попадают в файл. */
type Sheet = { data: XCell[][]; sheet: string; columns: { width: number }[] };

/** Все листы выгрузки в порядке вкладок анализа (пустые разделы пропущены). */
export function buildAuditWorkbook(a: AuditAnalysis): Sheet[] {
  // Без отчётности выгружать нечего — и это решается один раз здесь, а не в каждом
  // листе. Разделы вроде оценки честно печатают «не посчитано, вот препятствия», но
  // у дела без единого периода нет и разговора: файл из одних отказов не нужен.
  if (a.n === 0) return [];
  const p = a.periods.map(() => ({ width: 15 }));
  const wide = [{ width: 46 }, { width: 20 }];
  /**
   * Слои проверки считаются только у дела: свод группы идёт мимо конвейера
   * (`_consolidate` зовёт голый `analyze`), и его ответ несёт **умолчания** этих
   * полей. Без этой проверки в файл группы попали бы лист обязательств с нулями и
   * лист «оценка не посчитана» — то есть отчёт о проверке, которой не было. Признак
   * посчитанности — `summary.state`: его выставляет сама сводка.
   */
  const reviewed = a.summary.state === "ready";
  const dd: Array<[string, XCell[][], { width: number }[]]> = reviewed ? [
    ["Вердикт", verdictSheet(a), wide],
    ["Флаги", flagsSheet(a), [{ width: 46 }, { width: 14 }, { width: 18 },
                              { width: 18 }, { width: 46 }]],
    ["Качество прибыли", earningsSheet(a), [{ width: 46 }, ...p]],
    ["Обязательства", obligationsSheet(a), [{ width: 46 }, { width: 20 }, { width: 18 },
                                            { width: 18 }, { width: 30 }]],
    ["Оценка", valuationSheet(a), wide],
    ["Риски", riskSheet(a), [{ width: 46 }, { width: 20 }, { width: 20 }, { width: 20 }]],
    ["План-факт", planFactSheet(a), [{ width: 36 }, { width: 16 }, { width: 16 },
                                     { width: 16 }, { width: 12 }, { width: 22 }]],
  ] : [];
  const plan: Array<[string, XCell[][], { width: number }[]]> = [
    ...dd,
    ["Аналитическая форма", formSheet(a), [{ width: 44 }, ...p]],
    ["Тренды", trendsSheet(a), [{ width: 44 }, { width: 18 }, ...p]],
    ["Структура", structureSheet(a), [{ width: 44 }, ...p]],
    ["Коэффициенты", ratiosSheet(a), [{ width: 44 }, ...p]],
    ["Диагностика", diagnosticsSheet(a), [{ width: 44 }, { width: 22 }, ...p]],
    ["Методики", metricsSheet(a), [{ width: 44 }, ...p, { width: 30 }]],
    ["Заключение", opinionSheet(a), [{ width: 120 }]],
  ];
  return plan
    .filter(([, data]) => data.length > 0)
    .map(([sheet, data, columns]) => ({ sheet, data, columns }));
}

/** Скачать выгрузку анализа (write-excel-file грузится лениво — по клику). */
export async function downloadAuditXlsx(filename: string, a: AuditAnalysis): Promise<void> {
  const sheets = buildAuditWorkbook(a);
  // Пустая книга — не файл без листов, а сигнал, что выгружать нечего.
  if (sheets.length === 0) throw new Error("Анализ пуст — выгружать нечего");
  const writeXlsxFile = (await import("write-excel-file/browser")).default;
  await writeXlsxFile(sheets).toFile(filename);
}
