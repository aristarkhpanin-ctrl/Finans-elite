import { describe, expect, it } from "vitest";
import type { AuditAnalysis } from "./api/audit";
import {
  buildAuditWorkbook,
  diagnosticsSheet,
  earningsSheet,
  flagsSheet,
  formSheet,
  metricsSheet,
  obligationsSheet,
  planFactSheet,
  ratiosSheet,
  riskSheet,
  structureSheet,
  trendsSheet,
  valuationSheet,
  verdictSheet,
} from "./auditExport";

/** Ответ `/analyze` в объёме, достаточном для сборки листов. */
const analysis = (over: Partial<AuditAnalysis> = {}): AuditAnalysis => ({
  n: 2,
  periods: ["2023", "2024"],
  balance: [
    { code: "A_CASH", label: "Денежные средства", values: ["30", "50"], subtotal: false },
    { code: "A_TOTAL", label: "БАЛАНС (актив)", values: ["200", "250"], subtotal: true },
  ],
  income: [
    { code: "I_REVENUE", label: "Выручка", values: ["500", "600"], subtotal: false },
    { code: "I_NET", label: "Чистая прибыль", values: ["88", "110"], subtotal: true },
  ],
  horizontal: [{ code: "I_REVENUE", label: "Выручка", delta: [null, "100"], rate: [null, "0.2"] }],
  vertical: [{ code: "A_CASH", label: "Денежные средства", share: ["0.15", null] }],
  ratios: {
    liquidity: { "Коэффициент текущей ликвидности": ["2", null] },
    profitability: { "Рентабельность активов (ROA)": ["0.44", "0.44"] },
  },
  balance_gap: ["0", "0"],
  balanced: true,
  diagnostics: {
    light: "ok",
    summary: "Показатели в пределах нормативов.",
    scores: [{
      id: "altman_z1", name: "Модель Альтмана Z′", values: ["3.1", null],
      zones: ["safe", null], note: "Для непубличных компаний.",
    }],
    assessments: [{
      group: "liquidity", name: "Коэффициент текущей ликвидности", status: ["good", null],
    }],
  },
  user_metrics: [],
  revalued: false,
  opinion: "Первый абзац.\n\nВторой абзац.",
  warnings: [],
  input_issues: [],
  flags: { flags: [], priced_total: "0", unpriced: 0 },
  earnings: { base_code: "EBIT", reported: [], normalized: [], adjustments: [],
              grade: null, grade_note: "", deviation: null },
  obligations: { rows: [], balance_debt: "0", off_balance: "0", reported_debt: "0",
                 discrepancy: "0", reconciled: true, buckets: [], pledged_total: "0",
                 free_assets: null, pledged_share: null, covenants_breached: 0,
                 covenants_unknown: 0 },
  procedures: { items: [], total: 0, closed: 0, passed: 0, findings: 0, no_data: 0,
                done: 0, skipped: 0, pending: 0, coverage: null, limits: [] },
  summary: { state: "ready", verdict: "ok", headline: "", detail: "", coverage: null,
             open_procedures: 0, metrics: [], risk_flags: 0, warning_flags: 0,
             priced_total: "0", unpriced: 0, input_errors: 0,
             equity_value: null, asking_price: null, discount: null,
             not_computed: [] },
  valuation: { enabled: false, blockers: [], base_code: "EBIT", base_ebit: "0",
               wacc: "0", terminal_growth: "0", years: [], pv_forecast: "0",
               terminal_value: null, pv_terminal: null, enterprise_value: null,
               terminal_share: null, bridge: [], equity_value: null,
               implied_multiple: null, asking_price: null, discount: null,
               sensitivity: [], sensitivity_wacc: [], sensitivity_growth: [],
               equity_min: null, equity_max: null, warnings: [], not_computed: [] },
  risk: { available: false, blockers: [], base_price: null, step: "0.10",
          tornado: [], monte_carlo: null, warnings: [], not_computed: [] },
  plan_fact: { available: false, periods: [], rows: [], flags: [],
               predicted_total: "0", realized_total: "0", unpriced_realized: 0,
               orphan_marks: [], caveats: [], not_computed: [] },
  ...over,
});

/** Значения ячеек листа (null — пустая ячейка). */
const vals = (rows: ReturnType<typeof formSheet>) =>
  rows.map((r) => r.map((c) => (c === null ? null : c.value)));

const row = (rows: ReturnType<typeof formSheet>, first: string) =>
  vals(rows).find((r) => r[0] === first)!;

describe("formSheet", () => {
  it("заголовок периодов, разделы и подытоги жирным", () => {
    const rows = formSheet(analysis());
    expect(vals(rows)[0]).toEqual(["Статья", "2023", "2024"]);
    expect(vals(rows).some((r) => r[0] === "АНАЛИТИЧЕСКИЙ БАЛАНС")).toBe(true);
    expect(vals(rows).some((r) => r[0] === "ОТЧЁТ О ФИНАНСОВЫХ РЕЗУЛЬТАТАХ")).toBe(true);
    expect(row(rows, "Денежные средства")).toEqual(["Денежные средства", 30, 50]);
    const total = rows.find((r) => r[0] !== null && r[0].value === "БАЛАНС (актив)")!;
    expect(total[0] !== null && total[0].fontWeight).toBe("bold");
  });

  it("числа выгружаются числами (не текстом) — файл пригоден для расчётов", () => {
    const cash = formSheet(analysis()).find((r) => r[0] !== null && r[0].value === "Выручка")!;
    expect(cash[1]).toMatchObject({ value: 500, type: Number });
  });
});

describe("trendsSheet", () => {
  it("на статью — изменение и темп; база первого периода пуста, а не ноль", () => {
    const rows = trendsSheet(analysis());
    expect(vals(rows)[0]).toEqual(["Статья", "Показатель", "2023", "2024"]);
    expect(vals(rows)[1]).toEqual(["Выручка", "Изменение", null, 100]);
    expect(vals(rows)[2]).toEqual(["", "Темп прироста", null, 0.2]);
  });
});

describe("structureSheet", () => {
  it("доли по периодам; неопределённая доля — пустая ячейка", () => {
    expect(vals(structureSheet(analysis()))[1]).toEqual(["Денежные средства", 0.15, null]);
  });
});

describe("ratiosSheet", () => {
  it("группы в порядке вкладки, неопределённый коэффициент не подменяется нулём", () => {
    const rows = vals(ratiosSheet(analysis()));
    expect(rows[0]).toEqual(["Показатель", "2023", "2024"]);
    expect(rows.findIndex((r) => r[0] === "ЛИКВИДНОСТЬ"))
      .toBeLessThan(rows.findIndex((r) => r[0] === "РЕНТАБЕЛЬНОСТЬ"));
    expect(rows.find((r) => r[0] === "Коэффициент текущей ликвидности"))
      .toEqual(["Коэффициент текущей ликвидности", 2, null]);
  });

  it("пустые группы в файл не попадают", () => {
    const rows = vals(ratiosSheet(analysis({
      ratios: { liquidity: { "Коэффициент текущей ликвидности": ["2", "2"] }, gearing: {} },
    })));
    expect(rows.some((r) => r[0] === "ЛИКВИДНОСТЬ")).toBe(true);
    expect(rows.some((r) => r[0] === "ФИНАНСОВАЯ УСТОЙЧИВОСТЬ")).toBe(false);
  });

  it("доли выводятся процентным форматом, коэффициенты — числовым", () => {
    const rows = ratiosSheet(analysis());
    const roa = rows.find((r) => r[0] !== null && r[0].value === "Рентабельность активов (ROA)")!;
    expect(roa[1]).toMatchObject({ format: "0.0%" });
    const cur = rows.find((r) => r[0] !== null && r[0].value === "Коэффициент текущей ликвидности")!;
    expect(cur[1]).toMatchObject({ format: "0.0000" });
  });
});

describe("diagnosticsSheet", () => {
  it("светофор, скоринг со значением и зоной, оценки нормативов", () => {
    const rows = vals(diagnosticsSheet(analysis()));
    expect(rows[0]).toEqual(["Оценка", "Устойчивое состояние"]);
    expect(rows.find((r) => r[0] === "Модель Альтмана Z′"))
      .toEqual(["Модель Альтмана Z′", "Значение", 3.1, null]);
    expect(rows.find((r) => r[1] === "Зона")).toEqual(["", "Зона", "устойчивость", "—"]);
    expect(rows.find((r) => r[0] === "Коэффициент текущей ликвидности"))
      .toEqual(["Коэффициент текущей ликвидности", "liquidity", "норма", "—"]);
  });

  it("без диагностики лист пуст", () => {
    expect(diagnosticsSheet(analysis({ diagnostics: null }))).toEqual([]);
  });
});

describe("metricsSheet", () => {
  it("свои показатели с колонкой ошибки; без них лист пуст", () => {
    expect(metricsSheet(analysis())).toEqual([]);
    const rows = vals(metricsSheet(analysis({
      user_metrics: [{ name: "Своя маржа", values: ["0.1", "0.2"], error: null },
                     { name: "Сломанная", values: ["0", "0"], error: "неизвестная функция" }],
    })));
    expect(rows[0]).toEqual(["Показатель", "2023", "2024", "Ошибка"]);
    expect(rows[1]).toEqual(["Своя маржа", 0.1, 0.2, ""]);
    expect(rows[2]).toEqual(["Сломанная", 0, 0, "неизвестная функция"]);
  });
});

describe("Ядро due diligence в выгрузке", () => {
  /** Дело с находками, поправками прибыли, реестром и посчитанной оценкой. */
  const rich = () => analysis({
    flags: { flags: [
      { code: "receivables", severity: "risk", title: "Дебиторка растёт быстрее выручки",
        detail: "рост дебиторки опережает выручку", periods: [1], impact: "209",
        evidence: {} },
      { code: "negative_equity", severity: "risk", title: "Отрицательный капитал",
        detail: "", periods: [1], impact: null, evidence: {} },
    ], priced_total: "209", unpriced: 1 },
    summary: { state: "ready", verdict: "risk", headline: "Высокий риск",
               detail: "Находки уровня риска.", coverage: "0.64", open_procedures: 6,
               metrics: [], risk_flags: 2, warning_flags: 0, priced_total: "209",
               unpriced: 1, input_errors: 0, equity_value: null, asking_price: null,
               discount: null, not_computed: ["Доходность вложения — нужна цена сделки."] },
    procedures: { items: [], total: 28, closed: 18, passed: 12, findings: 6, no_data: 4,
                  done: 0, skipped: 0, pending: 6, coverage: "0.64", limits: [] },
    earnings: { base_code: "EBIT", reported: ["200", "220"], normalized: ["200", "196"],
                adjustments: [{ label: "Разовый доход", kind: "one_off",
                                kind_label: "Разовый доход или расход",
                                amounts: ["0", "-24"], total: "-24" }],
                grade: "B", grade_note: "", deviation: "-0.11" },
    obligations: { rows: [{ creditor: "Банк", contract: "К-1", kind: "loan",
                            kind_label: "Кредит", off_balance: false, amount: "520",
                            rate: "0.14", maturity: "2029", on_demand: false,
                            collateral: "", pledged_amount: "0", covenant: "",
                            covenant_status: "unknown", covenant_note: "" }],
                   balance_debt: "520", off_balance: "300", reported_debt: "500",
                   discrepancy: "20", reconciled: false, buckets: [],
                   pledged_total: "0", free_assets: null, pledged_share: null,
                   covenants_breached: 0, covenants_unknown: 1 },
    valuation: { ...analysis().valuation, enabled: true, enterprise_value: "1240",
                 wacc: "0.185", terminal_growth: "0.03", equity_min: "700",
                 equity_max: "1010", implied_multiple: "6.3", equity_value: "850",
                 bridge: [{ label: "Стоимость бизнеса (EV)", amount: "1240",
                            kind: "total", note: "" },
                          { label: "Долг по реестру", amount: "-520", kind: "subtract",
                            note: "" }] },
  });

  it("вердикт несёт охват проверки и список «что не посчитано»", () => {
    const rows = vals(verdictSheet(rich()));
    expect(rows[0]).toEqual(["Вердикт", "Высокий риск"]);
    expect(rows.find((r) => r[0] === "Охват проверки")).toEqual(["Охват проверки", "18 из 28"]);
    expect(rows.some((r) => String(r[0]).includes("не скидка к цене"))).toBe(true);
    expect(rows.some((r) => String(r[0]).includes("Доходность вложения"))).toBe(true);
  });

  it("флаг без денежной меры — пустая ячейка и слова, а не ноль", () => {
    // Ноль в колонке «оценка влияния» ушёл бы в чужую модель как посчитанная сумма.
    const rows = vals(flagsSheet(rich()));
    const noPrice = rows.find((r) => r[0] === "Отрицательный капитал")!;
    expect(noPrice[3]).toBeNull();
    expect(noPrice[4]).toBe("денежной меры нет");
    expect(rows.find((r) => r[0] === "Итого оценено")).toEqual(
      ["Итого оценено", null, null, 209, "без меры ещё 1"]);
  });

  it("периоды флага названы подписями, а не индексами", () => {
    expect(vals(flagsSheet(rich()))[1][2]).toBe("2024");
  });

  it("качество прибыли: отчётный ряд, поправки, нормализованный ряд", () => {
    const rows = vals(earningsSheet(rich()));
    expect(rows[0]).toEqual(["Показатель", "2023", "2024"]);
    expect(rows[1]).toEqual(["EBIT по отчёту", 200, 220]);
    expect(rows[2]).toEqual(["Разовый доход (Разовый доход или расход)", 0, -24]);
    expect(rows[3]).toEqual(["EBIT нормализованный", 200, 196]);
  });

  it("забалансовые обязательства названы отдельной строкой и не в сумме долга", () => {
    const rows = vals(obligationsSheet(rich()));
    expect(rows.find((r) => r[0] === "Долг по реестру (в балансе)")).toEqual(
      ["Долг по реестру (в балансе)", 520]);
    expect(rows.find((r) => String(r[0]).startsWith("Забалансовые"))).toEqual(
      ["Забалансовые (в сумму долга не входят)", 300]);
  });

  it("оценка выгружает мост и условия расчёта", () => {
    const rows = vals(valuationSheet(rich()));
    expect(rows[1]).toEqual(["Стоимость бизнеса (EV)", 1240]);
    expect(rows.find((r) => r[0] === "Ставка дисконтирования")).toEqual(
      ["Ставка дисконтирования", 0.185]);
    expect(rows.find((r) => r[0] === "Диапазон по чувствительности, до")).toEqual(
      ["Диапазон по чувствительности, до", 1010]);
  });

  it("непосчитанная оценка выгружает препятствия, а не нулевую цену", () => {
    const rows = vals(valuationSheet(analysis()));
    expect(rows[0][0]).toBe("Оценка не посчитана");
    expect(rows.every((r) => r.every((c) => typeof c !== "number"))).toBe(true);
  });

  it("Монте-Карло выгружается с условием, при котором его читают", () => {
    const rows = vals(riskSheet(analysis({
      risk: { available: true, blockers: [], base_price: "850", step: "0.10",
              tornado: [{ param: "growth", label: "Темп роста", step: "0.10",
                          low_price: "700", high_price: "1010", low_delta: "-150",
                          high_delta: "160", span: "310", note: "" }],
              monte_carlo: { iterations: 2000, valued: 1980, unvalued: 20,
                             median: "845", mean: "850", p10: "700", p25: "780",
                             p75: "910", p90: "1010", minimum: "600", maximum: "1200",
                             histogram: [], below_asking: null, median_drift: "0.01" },
              warnings: [], not_computed: [] },
    })));
    expect(rows.find((r) => r[0] === "Темп роста")).toEqual(["Темп роста", 700, 1010, 310]);
    expect(rows.find((r) => r[0] === "Оценки не вышло")).toEqual(["Оценки не вышло", 20]);
    expect(rows.some((r) => String(r[0]).includes("настолько хороши, насколько верны")))
      .toBe(true);
  });

  it("план-факт выгружается только при введённом плане и подписывает источники", () => {
    expect(planFactSheet(analysis())).toEqual([]);
    const rows = vals(planFactSheet(analysis({
      plan_fact: { available: true, periods: ["2023", "2024"],
                   rows: [{ code: "I_REVENUE", label: "Выручка", direction: "higher",
                            plan: "4000", fact: "3700", delta: "-300",
                            delta_share: "-0.075", verdict: "on_plan", note: "" }],
                   flags: [{ code: "receivables", title: "Дебиторка", severity: "risk",
                             predicted: "209", realized: true, actual_cost: "150",
                             note: "" }],
                   predicted_total: "209", realized_total: "150", unpriced_realized: 0,
                   orphan_marks: [], caveats: [], not_computed: [] },
    })));
    expect(rows[1]).toEqual(["Выручка", 4000, 3700, -300, -0.075, "в пределах порога"]);
    expect(rows.some((r) => String(r[0]).includes("посчитано платформой"))).toBe(true);
    expect(rows.some((r) => String(r[0]).includes("введены аналитиком"))).toBe(true);
  });
});

describe("buildAuditWorkbook", () => {
  it("листы в порядке чтения: сначала вывод и находки, потом числа", () => {
    // Тот же порядок, что в документе (SPEC, Прил. У.2). Пустые разделы пропущены:
    // в этом эталоне нет ни флагов, ни поправок прибыли, ни плана продавца.
    expect(buildAuditWorkbook(analysis()).map((s) => s.sheet)).toEqual([
      "Вердикт", "Обязательства", "Оценка",
      "Аналитическая форма", "Тренды", "Структура", "Коэффициенты", "Диагностика",
      "Заключение",
    ]);
  });

  it("пустые разделы пропускаются, ширины колонок совпадают с числом периодов", () => {
    const wb = buildAuditWorkbook(analysis({ diagnostics: null }));
    expect(wb.map((s) => s.sheet)).not.toContain("Диагностика");
    const form = wb.find((s) => s.sheet === "Аналитическая форма")!;
    expect(form.columns).toHaveLength(3);       // статья + 2 периода
  });

  it("свод группы не получает листов проверки: её там не было", () => {
    // У свода слои due diligence не считаются вовсе (`_consolidate` зовёт голый
    // `analyze`), и его ответ несёт умолчания. Лист обязательств с нулями и лист
    // «оценка не посчитана» были бы отчётом о проверке, которой не было.
    const group = analysis({ summary: { ...analysis().summary, state: "empty" } });
    const sheets = buildAuditWorkbook(group).map((s) => s.sheet);
    expect(sheets).not.toContain("Обязательства");
    expect(sheets).not.toContain("Оценка");
    expect(sheets).not.toContain("Вердикт");
    // Финансовое состояние свода выгружается как раньше.
    expect(sheets).toContain("Аналитическая форма");
    expect(sheets).toContain("Коэффициенты");
  });

  it("пустой анализ не даёт ни одного листа (пустой файл не выгружается)", () => {
    const empty = analysis({
      n: 0, periods: [], balance: [], income: [], horizontal: [], vertical: [],
      ratios: {}, balance_gap: [], diagnostics: null, opinion: "",
    });
    expect(buildAuditWorkbook(empty)).toEqual([]);
  });
});

describe("предупреждение о переоценке", () => {
  it("переоценённая выгрузка помечена в самом файле", () => {
    const rows = vals(formSheet(analysis({ revalued: true })));
    expect(String(rows[0][0])).toContain("переоценки статей");
    expect(rows[2]).toEqual(["Статья", "2023", "2024"]);   // заголовок сместился, не пропал
  });

  it("без переоценки лишней строки нет", () => {
    expect(vals(formSheet(analysis()))[0]).toEqual(["Статья", "2023", "2024"]);
  });
});
