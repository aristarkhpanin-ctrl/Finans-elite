import { describe, expect, it } from "vitest";
import {
  fmtAxis, fmtDateOnly, fmtMillions, fmtMoney, fmtRatio, fmtTable, fracToPct, initials, isShare,
  parseModelNumber,
  pctToFrac, percent,
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
  it("fmtAxis: дробная ось в миллионах не превращается в нули", () => {
    // Кривые чувствительности (P13, G15): деления −0,5…0 млн печатались «0» пять раз.
    const ticks = [-0.5, -0.375, -0.25, -0.125, 0].map((v) => fmtAxis(v, 0.125));
    expect(ticks).toEqual(["-0,50", "-0,38", "-0,25", "-0,13", "0,00"]);
    expect(new Set(ticks).size).toBe(5);
    expect(fmtAxis(2.5, 2.5)).toBe("2,5");                 // а не «3»
    expect(fmtAxis(-1e-17, 0.125)).toBe("0,00");          // ноль с погрешностью — ноль
    // Рубли и крупные шаги — как прежде: целые и сокращения.
    expect(fmtAxis(250, 250)).toBe("250");
    expect(fmtAxis(-54000, 80000)).toBe("-54к");
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

describe("fmtDateOnly — календарная дата без часового пояса", () => {
  it("день, месяц и год берутся из строки, а не из часового пояса", () => {
    // `new Date("2026-09-05")` — полночь UTC: западнее Гринвича документ напечатал бы
    // 04.09.2026. Дата документа и дата старта проекта уходят третьим лицам.
    expect(fmtDateOnly("2026-09-05")).toBe("05.09.2026");
    expect(fmtDateOnly("2026-01-01")).toBe("01.01.2026");
  });

  it("полная отметка времени тоже читается по календарной части", () => {
    expect(fmtDateOnly("2026-09-05T23:30:00Z")).toBe("05.09.2026");
  });

  it("пусто и непонятное — прочерк, а не выдуманная дата", () => {
    expect(fmtDateOnly(null)).toBe("—");
    expect(fmtDateOnly(undefined)).toBe("—");
    expect(fmtDateOnly("")).toBe("—");
    expect(fmtDateOnly("вчера")).toBe("—");
  });
});


describe("parseModelNumber / isShare — русское написание, как на сервере", () => {
  it("запятая и пробелы в разрядах читаются, мусор — NaN, а не ноль", () => {
    expect(parseModelNumber("0,5")).toBe(0.5);
    expect(parseModelNumber("1 200,50")).toBe(1200.5);
    expect(parseModelNumber("1\u00a0200")).toBe(1200);
    expect(parseModelNumber(0.3)).toBe(0.3);
    expect(Number.isNaN(parseModelNumber("полтора"))).toBe(true);
  });

  it("доля «0,5» — в диапазоне: сервер её примет, и экран не спорит", () => {
    expect(isShare("0,5")).toBe(true);
    expect(isShare("1")).toBe(true);
    expect(isShare(undefined)).toBe(true);
    expect(isShare("1,5")).toBe(false);
    expect(isShare("-0,1")).toBe(false);
    expect(isShare("полтора")).toBe(false);
  });
});

describe("initials — буквы, а не первый символ слова", () => {
  it("кавычка в названии организации не становится инициалом", () => {
    expect(initials("ООО «Матрица»")).toBe("ОМ");
    expect(initials("Финмодель Консалтинг")).toBe("ФК");
    expect(initials("  иван   петров  сидоров ")).toBe("ИП");
    expect(initials("ivan@example.test")).toBe("I");
  });

  it("пусто и одни знаки — запасной символ", () => {
    expect(initials("")).toBe("•");
    expect(initials(null)).toBe("•");
    expect(initials("«» —", "?")).toBe("?");
  });
});
