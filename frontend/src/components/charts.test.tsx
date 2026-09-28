// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CalcResponse } from "../api/calc";
import { CHART_MIN_W, fitWidth, HistogramChart, MultiLineChart, type P } from "./charts";
import { ResultCharts } from "./ResultCharts";

/**
 * Графики строятся в ширину своего места, а не в ширину макета. Матрица скриншотов P13
 * (G15) показала, что `viewBox` 1100×240 на телефоне вписывался в карточку целиком и
 * становился полосой с подписями в 3px. Раскладки в jsdom нет — ширину места задаёт тест.
 */

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const base: P = { w: 1100, h: 240, mL: 54, mR: 18, mT: 18, mB: 26 };

/** Место графика шириной `width` (так его увидел бы браузер). */
function placeWidth(width: number) {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
    { width, height: 260, top: 0, left: 0, right: width, bottom: 260, x: 0, y: 0, toJSON: () => ({}) },
  );
}

const viewBoxes = (el: HTMLElement) => [...el.querySelectorAll("svg")].map((s) => s.getAttribute("viewBox"));

describe("fitWidth", () => {
  it("пока ширина неизвестна — геометрия макета", () => {
    expect(fitWidth(base, null)).toBe(base);
  });

  it("ширина места, а не макета; высота и поля — прежние", () => {
    expect(fitWidth(base, 780)).toEqual({ ...base, w: 780 });
  });

  it("у́же предела не сжимается: подписи оси налезли бы друг на друга", () => {
    expect(fitWidth(base, 300)).toEqual({ ...base, w: CHART_MIN_W });
  });
});

describe("графики меряют своё место", () => {
  it("гистограмма Монте-Карло", () => {
    placeWidth(338);
    const { container } = render(<HistogramChart bins={[{ from: -1, to: 0, count: 3 }, { from: 0, to: 1, count: 5 }]} />);
    expect(viewBoxes(container)).toEqual([`0 0 ${CHART_MIN_W} 240`]);
  });

  it("кривые чувствительности", () => {
    placeWidth(780);
    const { container } = render(
      <MultiLineChart labels={["0,9", "1", "1,1"]}
                      series={[{ key: "a", label: "Цена", color: "red", values: [1, 2, 3] }]} />,
    );
    expect(viewBoxes(container)).toEqual(["0 0 780 260"]);
  });

  it("карточки результатов — все, кроме кольца издержек", () => {
    placeWidth(780);
    const empty = { lines: [] };
    const result = {
      n: 2, income: empty, cashflow: empty, balance: empty, profit_use: empty,
      metrics: { pb_months: null },
      valuation: { net_assets: "1000000", gordon_value: null, dividend_value: null,
                   earnings_multiple_value: null, liquidation_value: null },
    } as unknown as CalcResponse;
    const { container } = render(<ResultCharts result={result} />);
    const widths = viewBoxes(container).map((v) => Number(v?.split(" ")[2]));
    // Денежный поток, окупаемость, прибыль, активы и оценка — по месту; кольцо — своё.
    expect(widths.filter((w) => w === 780)).toHaveLength(5);
    expect(widths).toContain(340);
  });
});
