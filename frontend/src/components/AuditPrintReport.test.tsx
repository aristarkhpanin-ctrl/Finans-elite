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
    ...over,
  } as AuditAnalysis;
}

const paper = (over: Partial<AuditAnalysis> = {}) =>
  render(<AuditPrintReport analysis={analysis(over)} name="ООО «Цель»"
                           industry="Перевозки" standard="rsbu" />);

describe("Печатное заключение", () => {
  it("два листа и реквизиты дела в шапке", () => {
    paper();
    expect(document.querySelectorAll(".ap-paper")).toHaveLength(2);
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

  it("оговорка о характере документа есть на листе", () => {
    // Заключение не аудиторское в смысле закона — это должно быть на бумаге,
    // потому что бумагу показывают третьим лицам без всякого контекста.
    paper();
    expect(screen.getByText(/не является аудиторским/)).toBeTruthy();
  });
});
