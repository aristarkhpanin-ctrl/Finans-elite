import { describe, expect, it } from "vitest";
import {
  fmtAxis,
  fmtMillions,
  fmtMoney,
  fmtRatio,
  fmtTable,
  fracToPct,
  pctToFrac,
  percent,
} from "./format";

const NBSP = String.fromCharCode(0xa0); // NBSP (\u00A0)

describe("fmtTable", () => {
  it("ноль и null → «—» (kind zero)", () => {
    expect(fmtTable(0)).toEqual({ text: "—", kind: "zero" });
    expect(fmtTable(null)).toEqual({ text: "—", kind: "zero" });
    expect(fmtTable(0.4)).toEqual({ text: "—", kind: "zero" }); // округляется к 0
  });
  it("положительные — с группировкой NBSP", () => {
    expect(fmtTable(1234567)).toEqual({ text: `1${NBSP}234${NBSP}567`, kind: "pos" });
    expect(fmtTable("2500")).toEqual({ text: `2${NBSP}500`, kind: "pos" });
  });
  it("отрицательные — в скобках", () => {
    expect(fmtTable(-1234)).toEqual({ text: `(1${NBSP}234)`, kind: "neg" });
  });
});

describe("fmtMoney / fmtMillions / fmtAxis / fmtRatio", () => {
  it("fmtMoney: группировка, типографский минус, ₽", () => {
    expect(fmtMoney(12480000)).toBe(`12${NBSP}480${NBSP}000${NBSP}₽`);
    expect(fmtMoney(-5)).toBe(`−5${NBSP}₽`);
    expect(fmtMoney(null)).toBe("—");
  });
  it("fmtMillions: знак и разряд млн", () => {
    expect(fmtMillions(-4200000)).toBe(`−4,2${NBSP}млн${NBSP}₽`);
    expect(fmtMillions(18400000, { sign: true })).toBe(`+18,4${NBSP}млн${NBSP}₽`);
    expect(fmtMillions(null)).toBe("—");
  });
  it("fmtAxis: короткие подписи осей", () => {
    expect(fmtAxis(8400000)).toBe("8,4м");
    expect(fmtAxis(12000000)).toBe("12м");
    expect(fmtAxis(320000)).toBe("320к");
    expect(fmtAxis(500)).toBe("500");
  });
  it("fmtRatio: запятая-десятичная, фикс. знаки", () => {
    expect(fmtRatio(1.2345)).toBe("1,23");
    expect(fmtRatio(-0.5)).toBe("−0,50");
    expect(fmtRatio(2, 0)).toBe("2");
    expect(fmtRatio(null)).toBe("—");
  });
  it("percent: доля → %", () => {
    expect(percent("0.205")).toBe("20,5%");
    expect(percent(null)).toBe("—");
  });
});

// Ключевое: конвертация доля↔проценты строковым сдвигом точки, БЕЗ плавающей точки.
describe("fracToPct / pctToFrac (точный сдвиг)", () => {
  it("доля → проценты", () => {
    expect(fracToPct("0.205")).toBe("20.5");
    expect(fracToPct("0.2")).toBe("20");
    expect(fracToPct("1")).toBe("100");
    expect(fracToPct("0")).toBe("0");
    expect(fracToPct("-0.2")).toBe("-20");
    expect(fracToPct("")).toBe("");
    expect(fracToPct("мусор")).toBe("");
  });
  it("проценты → доля (в т.ч. запятая)", () => {
    expect(pctToFrac("20.5")).toBe("0.205");
    expect(pctToFrac("20,5")).toBe("0.205");
    expect(pctToFrac("20")).toBe("0.2");
    expect(pctToFrac("100")).toBe("1");
    expect(pctToFrac("2.5")).toBe("0.025");
    expect(pctToFrac("0")).toBe("0");
    expect(pctToFrac("")).toBe("");
  });
  it("без ошибки округления float (0.07 → «7», не «7.000000000000001»)", () => {
    expect(fracToPct("0.07")).toBe("7");
    expect(fracToPct("0.29")).toBe("29");
    expect(pctToFrac("7")).toBe("0.07");
  });
  it("круговая конвертация сохраняет значение", () => {
    for (const frac of ["0.205", "0.07", "0.1", "0.015", "1"]) {
      expect(pctToFrac(fracToPct(frac))).toBe(frac);
    }
  });
});
