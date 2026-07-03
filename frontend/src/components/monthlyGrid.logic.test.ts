import { describe, expect, it } from "vitest";
import { applyPaste, fmtAgg, fmtInt, norm, num, plural, splitPasted } from "./monthlyGrid.logic";

const NBSP = String.fromCharCode(0xa0); //

describe("num / norm", () => {
  it("num: убирает пробелы (в т.ч. NBSP), запятая → точка", () => {
    expect(num("1 234,5")).toBe(1234.5);
    expect(num(`1${NBSP}234`)).toBe(1234);
    expect(num("")).toBe(0);
    expect(num(undefined)).toBe(0);
    expect(num("мусор")).toBe(0);
  });
  it("norm: строка → канонический вид с точкой", () => {
    expect(norm(" 2,5 ")).toBe("2.5");
    expect(norm(`1${NBSP}234,75`)).toBe("1234.75");
  });
});

describe("fmtInt / fmtAgg / plural", () => {
  it("fmtInt: группировка NBSP, типографский минус", () => {
    expect(fmtInt(1234567)).toBe(`1${NBSP}234${NBSP}567`);
    expect(fmtInt(-1234)).toBe(`−1${NBSP}234`);
  });
  it("fmtAgg: млн для крупных сумм", () => {
    expect(fmtAgg(12400000)).toBe(`12,40${NBSP}млн`);
    expect(fmtAgg(5000)).toBe(`5${NBSP}000`);
  });
  it("plural: русские формы", () => {
    const f = (n: number) => plural(n, "значение", "значения", "значений");
    expect(f(1)).toBe("значение");
    expect(f(2)).toBe("значения");
    expect(f(5)).toBe("значений");
    expect(f(11)).toBe("значений");
    expect(f(21)).toBe("значение");
    expect(f(114)).toBe("значений");
  });
});

describe("splitPasted", () => {
  it("делит по табам/переводам строк/;, обрезает и отбрасывает пустые", () => {
    expect(splitPasted("1\t2\t3")).toEqual(["1", "2", "3"]);
    expect(splitPasted("1\n2\r\n3")).toEqual(["1", "2", "3"]);
    expect(splitPasted("1; 2 ;3")).toEqual(["1", "2", "3"]);
    expect(splitPasted("1\t\t2")).toEqual(["1", "2"]);
    expect(splitPasted("  5  ")).toEqual(["5"]);
  });
});

describe("applyPaste", () => {
  it("одно значение → null (обычная вставка браузером)", () => {
    expect(applyPaste(["", "", ""], 0, "42", 3)).toBeNull();
  });
  it("диапазон с начала — заполняет и нормализует", () => {
    expect(applyPaste(["", "", "", ""], 0, "10\t20\t30", 4)).toEqual({
      values: ["10", "20", "30", ""],
      filled: 3,
    });
  });
  it("вставка со смещением сохраняет остальные ячейки", () => {
    expect(applyPaste(["a", "b", "c", "d"], 1, "5\t6", 4)).toEqual({
      values: ["a", "5", "6", "d"],
      filled: 2,
    });
  });
  it("десятичная запятая нормализуется в точку", () => {
    expect(applyPaste(["", "", ""], 0, "1,5\t2,5", 3)).toEqual({
      values: ["1.5", "2.5", ""],
      filled: 2,
    });
  });
  it("перебор за границу ряда обрезается (filled = сколько влезло)", () => {
    expect(applyPaste(["", "", ""], 2, "1\t2\t3", 3)).toEqual({
      values: ["", "", "1"],
      filled: 1,
    });
  });
});
