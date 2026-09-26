import { describe, expect, it } from "vitest";
import {
  aggregateFlowSeries,
  aggregateStatement,
  defaultPeriod,
  periodChunks,
  periodLabels,
} from "./aggregate";
import type { StatementOut } from "./api/calc";

const stmt = (lines: [string, string[]][]): StatementOut => ({
  lines: lines.map(([code, values]) => ({ code, label: code, values })),
});

const values = (s: StatementOut, code: string) =>
  s.lines.find((l) => l.code === code)!.values;

describe("periodChunks / periodLabels / defaultPeriod", () => {
  it("режет горизонт на периоды, последний неполный", () => {
    expect(periodChunks(7, "quarter")).toEqual([[0, 3], [3, 6], [6, 7]]);
    expect(periodChunks(24, "year")).toEqual([[0, 12], [12, 24]]);
    expect(periodChunks(3, "month")).toEqual([[0, 1], [1, 2], [2, 3]]);
  });

  it("метки: М/К/Год от старта проекта", () => {
    expect(periodLabels(3, "month")).toEqual(["М1", "М2", "М3"]);
    expect(periodLabels(7, "quarter")).toEqual(["К1", "К2", "К3"]);
    expect(periodLabels(30, "year")).toEqual(["Год 1", "Год 2", "Год 3"]);
  });

  it("дефолт по горизонту: месяц ≤ 24, квартал ≤ 72, дальше год", () => {
    expect(defaultPeriod(12)).toBe("month");
    expect(defaultPeriod(24)).toBe("month");
    expect(defaultPeriod(36)).toBe("quarter");
    expect(defaultPeriod(72)).toBe("quarter");
    expect(defaultPeriod(120)).toBe("year");
  });
});

describe("aggregateStatement", () => {
  it("month возвращает исходный отчёт", () => {
    const s = stmt([["I1", ["1", "2"]]]);
    expect(aggregateStatement(s, "flow", 2, "month")).toBe(s);
  });

  it("потоки — суммы; копейки складываются точно", () => {
    const s = stmt([["I1", ["0.10", "0.20", "0.30", "5"]]]);
    const agg = aggregateStatement(s, "flow", 4, "quarter");
    expect(values(agg, "I1")).toEqual(["0.6", "5"]);   // 0.1+0.2+0.3 без артефактов float
  });

  it("баланс — конец периода", () => {
    const s = stmt([["B1", ["1", "2", "3", "4", "5", "6"]]]);
    const agg = aggregateStatement(s, "balance", 6, "quarter");
    expect(values(agg, "B1")).toEqual(["3", "6"]);
  });

  it("C28 — начало периода, C29 — конец; тождество года сохраняется", () => {
    const s = stmt([
      ["C13", ["10", "10", "10", "10", "10", "10"]],
      ["C28", ["100", "110", "120", "130", "140", "150"]],
      ["C29", ["110", "120", "130", "140", "150", "160"]],
    ]);
    const agg = aggregateStatement(s, "flow", 6, "quarter");
    expect(values(agg, "C28")).toEqual(["100", "130"]);
    expect(values(agg, "C29")).toEqual(["130", "160"]);  // C28 + ΣC13 = C29 в периоде
  });

  it("P2 — начало, P7 — конец, P3 = P2 + ΣP1", () => {
    const s = stmt([
      ["P1", ["5", "5", "5", "5"]],
      ["P2", ["100", "105", "110", "115"]],
      ["P3", ["105", "110", "115", "120"]],
      ["P7", ["105", "110", "115", "120"]],
    ]);
    const agg = aggregateStatement(s, "flow", 4, "quarter");
    expect(values(agg, "P2")).toEqual(["100", "115"]);
    expect(values(agg, "P3")).toEqual(["115", "120"]);   // P2 периода + ΣP1 периода
    expect(values(agg, "P7")).toEqual(["115", "120"]);   // = P3 (выплат нет) — тождество
  });
});

describe("aggregateFlowSeries", () => {
  it("суммирует произвольный ряд по периодам", () => {
    expect(aggregateFlowSeries(["1", "2", "3", "4"], 4, "quarter")).toEqual(["6", "4"]);
    const same = ["1", "2"];
    expect(aggregateFlowSeries(same, 2, "month")).toBe(same);
  });
});
