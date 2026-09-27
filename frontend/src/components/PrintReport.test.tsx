// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CalcResponse, StatementOut } from "../api/calc";
import { PRINT_COLS, printPageCount, printSheets, PrintReport } from "./PrintReport";

/**
 * Печатный отчёт. Матрица скриншотов P13 (G15) показала, что 24 месяца в одну строку
 * давали колонку 33px, и шестизначные числа соседних месяцев печатались друг поверх
 * друга. Лист держит не больше PRINT_COLS колонок, длинный ряд продолжается на следующем,
 * а период — тот же, что на экране.
 */

afterEach(cleanup);

const stmt = (codes: string[], n: number): StatementOut => ({
  lines: codes.map((code) => ({ code, label: code, values: Array.from({ length: n }, () => "100000") })),
});

function result(n: number): CalcResponse {
  return {
    n,
    engine_version: "0.9.45",
    income: stmt(["I1", "I28"], n),
    cashflow: stmt(["C1", "C29"], n),
    balance: stmt(["B1", "B20"], n),
    profit_use: stmt(["P1", "P2", "P3"], n),
    metrics: { npv: "1", irr_annual: null, pi: null, pb_months: null, dpb_months: null,
               peak_financing_need: null, no_return_metrics_note: null },
    valuation: { net_assets: "1", gordon_value: null, dividend_value: null,
                 earnings_multiple_value: null, liquidation_value: null },
  } as unknown as CalcResponse;
}

/** Колонки периодов на каждом листе отчёта. */
const sheetColumns = (el: HTMLElement) =>
  [...el.querySelectorAll(".pr-paper")].slice(1).map(
    (p) => [...p.querySelectorAll(".pr-tmonth")].map((c) => c.textContent),
  );

describe("раскладка листов", () => {
  it("год помесячно — по листу на отчёт, как в макете", () => {
    expect(printSheets(12, "month").map((s) => [s.key, s.from, s.to])).toEqual([
      ["income", 0, 12], ["cashflow", 0, 12], ["balance", 0, 12], ["profit_use", 0, 12],
    ]);
    expect(printPageCount(12, "month")).toBe(5);
  });

  it("длинный ряд продолжается на следующем листе, а не сужает колонки", () => {
    const income = printSheets(30, "month").filter((s) => s.key === "income");
    expect(income.map((s) => [s.from, s.to])).toEqual([[0, 12], [12, 24], [24, 30]]);
    expect(printPageCount(30, "month")).toBe(1 + 4 * 3);
  });

  it("свёрнутый период — меньше листов", () => {
    expect(printPageCount(24, "year")).toBe(5);
    expect(printPageCount(36, "quarter")).toBe(5);
  });
});

describe("печать", () => {
  it("24 месяца: на листе не больше PRINT_COLS колонок, продолжение названо", () => {
    const { container, getAllByText } = render(<PrintReport data={result(24)} title="Склад" period="month" />);
    const cols = sheetColumns(container);
    expect(cols).toHaveLength(8);
    expect(Math.max(...cols.map((c) => c.length))).toBe(PRINT_COLS);
    expect(cols[1][0]).toBe("М13");
    expect(getAllByText(/помесячно · М13–М24/)).toHaveLength(4);
    expect(getAllByText("стр. 9 / 9")).toHaveLength(1);
  });

  it("период — как на экране: по годам суммы свёрнуты той же свёрткой", () => {
    const { container, getAllByText } = render(<PrintReport data={result(24)} title="Склад" period="year" />);
    expect(sheetColumns(container)[0]).toEqual(["Год 1", "Год 2"]);
    // Выручка года — сумма двенадцати месяцев по 100 000 (разряды — неразрывным пробелом).
    const income = container.querySelectorAll(".pr-paper")[1];
    expect(income.textContent).toContain("1 200 000");
    expect(getAllByText(/по годам проекта/).length).toBeGreaterThan(0);
  });

  it("без периода — по горизонту, как отчёты на экране", () => {
    const { container } = render(<PrintReport data={result(12)} title="Склад" />);
    expect(sheetColumns(container)).toHaveLength(4);
    expect(sheetColumns(container)[0][11]).toBe("М12");
  });
});
