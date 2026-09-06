// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { AuditAnalysis } from "../api/audit";
import { AuditPrintReport } from "./AuditPrintReport";

/**
 * Печатное заключение. Проверяется то, что отличает бумагу от экрана: отрицательные
 * значения в скобках, неопределённый показатель прочерком, оговорки на листе, размер
 * страницы живёт только пока экран открыт.
 */

afterEach(cleanup);

function analysis(over: Partial<AuditAnalysis> = {}): AuditAnalysis {
  return {
    n: 2,
    periods: ["2023", "2024"],
    balance: [
      { code: "A_TOTAL", label: "СУММАРНЫЙ АКТИВ", values: ["200", "250"], subtotal: true },
      { code: "P_EQUITY", label: "Капитал", values: ["120", "-40"], subtotal: false },
    ],
    income: [
      { code: "I_REVENUE", label: "Выручка", values: ["500", "600"], subtotal: false },
      { code: "I_NET", label: "Чистая прибыль", values: ["88", "-15"], subtotal: true },
    ],
    horizontal: [], vertical: [],
    ratios: {
      liquidity: { "Коэффициент текущей ликвидности": ["2", "1.4567"] },
      gearing: { "Коэффициент автономии": ["0.6", null] },
    },
    balance_gap: ["0", "0"], balanced: true,
    diagnostics: {
      light: "risk", summary: "Признаки неустойчивости",
      scores: [{ id: "z2", name: "Альтман Z″", values: ["1.1", "0.9"],
                 zones: ["grey", "distress"], note: "" }],
      assessments: [],
    },
    user_metrics: [], revalued: false, opinion: "Первый абзац.\n\nВторой абзац.",
    warnings: [], input_issues: [],
    flags: { flags: [
      { code: "receivables_outpace_revenue", severity: "risk",
        title: "Дебиторка растёт быстрее выручки", detail: "", periods: [1],
        impact: "209", evidence: {} },
      { code: "negative_equity", severity: "risk", title: "Отрицательный капитал",
        detail: "", periods: [1], impact: null, evidence: {} },
    ], priced_total: "209", unpriced: 1 },
    earnings: { base_code: "EBIT", reported: ["100", "120"],
                normalized: ["100", "96"], adjustments: [], grade: "B",
                grade_note: "", deviation: "-0.2" },
    obligations: { rows: [], balance_debt: "520", off_balance: "300",
                   reported_debt: "500", discrepancy: "20", reconciled: false,
                   buckets: [], pledged_total: "0", free_assets: null,
                   pledged_share: null, covenants_breached: 0, covenants_unknown: 0 },
    procedures: { items: [], total: 28, closed: 18, passed: 12, findings: 6,
                  no_data: 4, done: 0, skipped: 0, pending: 6, coverage: "0.64",
                  limits: ["Судебные дела и претензии — процедура не выполнена."] },
    summary: { state: "ready", verdict: "risk", headline: "Высокий риск",
               detail: "Есть находки уровня риска.", coverage: "0.64",
               open_procedures: 6, metrics: [], risk_flags: 2, warning_flags: 0,
               priced_total: "209", unpriced: 1, input_errors: 0,
               equity_value: null, asking_price: null, discount: null,
               not_computed: [] },
    valuation: { enabled: false, blockers: ["Оценка выключена в допущениях дела."],
                 base_code: "EBIT", base_ebit: "0", wacc: "0", terminal_growth: "0",
                 years: [], pv_forecast: "0", terminal_value: null, pv_terminal: null,
                 enterprise_value: null, terminal_share: null, bridge: [],
                 equity_value: null, implied_multiple: null, asking_price: null,
                 discount: null, sensitivity: [], sensitivity_wacc: [],
                 sensitivity_growth: [], equity_min: null, equity_max: null,
                 warnings: [], not_computed: [] },
    risk: { available: false, blockers: [], base_price: null, step: "0.10",
            tornado: [], monte_carlo: null, warnings: [], not_computed: [] },
    plan_fact: { available: false, periods: [], rows: [], flags: [],
                 predicted_total: "0", realized_total: "0", unpriced_realized: 0,
                 orphan_marks: [], caveats: [], not_computed: [] },
    ...over,
  } as AuditAnalysis;
}

const paper = (over: Partial<AuditAnalysis> = {}) =>
  render(<AuditPrintReport analysis={analysis(over)} name="ООО «Цель»"
                           industry="Перевозки" standard="rsbu" />);

describe("Печатное заключение", () => {
  it("три листа и реквизиты дела в шапке", () => {
    paper();
    // Вывод · находки · показатели. Номер листа считается, а не пишется руками.
    expect(document.querySelectorAll(".ap-paper")).toHaveLength(3);
    expect(screen.getByText("3 / 3")).toBeTruthy();
    expect(screen.getByText("ООО «Цель»")).toBeTruthy();
    expect(screen.getByText(/Перевозки · РСБУ/)).toBeTruthy();
  });

  it("отрицательные значения печатаются в скобках, а не с минусом", () => {
    // На бумаге минус теряется при копировании и на плохой печати — скобки нет.
    paper();
    expect(screen.getByText("(40)")).toBeTruthy();
    expect(screen.getByText("(15)")).toBeTruthy();
    expect(screen.queryByText("-40")).toBeNull();
  });

  it("неопределённый коэффициент — прочерк, а не ноль", () => {
    // Ноль означал бы «посчитано и вышло ноль», а показатель не определён вовсе.
    paper();
    const rows = [...document.querySelectorAll(".ap-table tr")]
      .map((r) => r.textContent ?? "");
    expect(rows.find((r) => r.includes("Коэффициент автономии"))).toContain("—");
  });

  it("показатели берутся за последний период", () => {
    paper();
    expect(screen.getByText(/по данным за 2024/)).toBeTruthy();
    expect(screen.getByText("Показатели за 2024")).toBeTruthy();
    // ликвидность последнего периода 1.4567 → 1,46, а не 2 (первый период)
    const rows = [...document.querySelectorAll(".ap-table tr")].map((r) => r.textContent ?? "");
    expect(rows.find((r) => r.includes("текущей ликвидности"))).toContain("1,46");
  });

  it("оговорки печатаются на бумаге, а не только на экране", () => {
    // Документ уходит из системы и обязан нести те же предупреждения, что результат.
    paper({ revalued: true, balanced: false });
    expect(screen.getByText(/с учётом переоценки статей/)).toBeTruthy();
    expect(screen.getByText(/Баланс не сходится/)).toBeTruthy();
  });

  it("без оговорок лишних плашек нет", () => {
    paper();
    expect(screen.queryByText(/с учётом переоценки/)).toBeNull();
    expect(screen.queryByText(/Баланс не сходится/)).toBeNull();
  });

  it("размер страницы задаётся только пока бланк открыт", () => {
    // Иначе правило перевернуло бы и альбомный отчёт первого продукта.
    const view = paper();
    const style = document.head.querySelector("style[data-audit-print]");
    expect(style?.textContent).toContain("A4 portrait");
    view.unmount();
    expect(document.head.querySelector("style[data-audit-print]")).toBeNull();
  });

  it("зона модели названа словом, а не кодом", () => {
    paper();
    expect(screen.getByText("зона риска")).toBeTruthy();
  });

  it("вердикт по делу и охват проверки — на первом листе", () => {
    // Охват меняет чтение вывода: «18 из 28» внизу последней страницы прочтут
    // уже после того, как решение принято.
    paper();
    // «Высокий риск» стоит и в светофоре состояния — сверяем именно блок вердикта.
    const block = screen.getByText("Вердикт по делу").closest(".ap-block")!;
    expect(block.textContent).toContain("Высокий риск");
    expect(block.textContent).toContain("Есть находки уровня риска");
    const rows = [...document.querySelectorAll(".ap-table tr")].map((r) => r.textContent ?? "");
    expect(rows.find((r) => r.includes("Охват проверки"))).toContain("18 из 28");
  });

  it("сумма оценённых флагов не выдаётся за скидку к цене", () => {
    paper();
    expect(screen.getByText(/Оценённое влияние флагов — не скидка к цене/)).toBeTruthy();
    expect(screen.getByText(/Ещё 1 флаг денежной меры не имеют/)).toBeTruthy();
  });

  it("реестр флагов на бумаге, и флаг без меры — не ноль рублей", () => {
    paper();
    expect(screen.getByText("Дебиторка растёт быстрее выручки")).toBeTruthy();
    expect(screen.getByText("меры нет")).toBeTruthy();
  });

  it("забалансовые обязательства названы отдельно и не в сумме долга", () => {
    paper();
    const rows = [...document.querySelectorAll(".ap-table tr")].map((r) => r.textContent ?? "");
    expect(rows.find((r) => r.includes("Забалансовые"))).toContain("не в сумме");
    expect(rows.find((r) => r.includes("Долг по реестру"))).toContain("520");
  });

  it("оценки нет — печатается препятствие, а не нулевая цена", () => {
    paper();
    expect(screen.getByText("Оценка не посчитана.")).toBeTruthy();
    expect(screen.getByText(/Оценка выключена в допущениях дела/)).toBeTruthy();
  });

  it("посчитанная оценка печатает мост и условия расчёта", () => {
    paper({ valuation: { ...analysis().valuation, enabled: true,
                         enterprise_value: "1240", wacc: "0.185",
                         terminal_growth: "0.03", equity_min: "930",
                         equity_max: "1140", discount: "0.18",
                         bridge: [{ label: "Стоимость бизнеса (EV)", amount: "1240",
                                    kind: "total", note: "" },
                                  { label: "Долг", amount: "-520", kind: "subtract",
                                    note: "" }] } });
    expect(screen.getByText("Стоимость бизнеса (EV)")).toBeTruthy();
    expect(screen.getByText(/ставка дисконтирования 18,5%/)).toBeTruthy();
    expect(screen.getByText(/Диапазон по чувствительности/)).toBeTruthy();
  });

  it("границы проверки печатаются, а не остаются на экране", () => {
    // Умолчание о непроверенном читатель документа принимает за проверенное.
    paper();
    expect(screen.getByText("Границы проверки")).toBeTruthy();
    expect(screen.getByText(/Судебные дела и претензии/)).toBeTruthy();
  });

  it("оговорка о характере документа есть на листе", () => {
    // Заключение не аудиторское в смысле закона — это должно быть на бумаге,
    // потому что бумагу показывают третьим лицам без всякого контекста.
    paper();
    expect(screen.getByText(/не является аудиторским/)).toBeTruthy();
  });
});
