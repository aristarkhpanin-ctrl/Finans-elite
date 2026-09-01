import { describe, expect, it } from "vitest";
import type { AuditAnalysis } from "./api/audit";
import {
  buildAuditWorkbook,
  diagnosticsSheet,
  formSheet,
  metricsSheet,
  ratiosSheet,
  structureSheet,
  trendsSheet,
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

describe("buildAuditWorkbook", () => {
  it("листы в порядке вкладок анализа", () => {
    expect(buildAuditWorkbook(analysis()).map((s) => s.sheet)).toEqual([
      "Аналитическая форма", "Тренды", "Структура", "Коэффициенты", "Диагностика", "Заключение",
    ]);
  });

  it("пустые разделы пропускаются, ширины колонок совпадают с числом периодов", () => {
    const wb = buildAuditWorkbook(analysis({ diagnostics: null }));
    expect(wb.map((s) => s.sheet)).not.toContain("Диагностика");
    const form = wb.find((s) => s.sheet === "Аналитическая форма")!;
    expect(form.columns).toHaveLength(3);       // статья + 2 периода
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
