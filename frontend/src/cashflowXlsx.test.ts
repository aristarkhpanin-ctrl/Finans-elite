import { describe, expect, it } from "vitest";
import type { Actualization } from "./api/model";
import {
  applyCashflow, articleKey, buildCashflowTemplate, FACT_LINES, monthLabels, monthOf,
  parseCashflowRows, suggest,
} from "./cashflowXlsx";

/**
 * Факт ДДС из Excel и 1С (L7). Проверяется то, на чём такой импорт обычно врёт молча:
 * колонка-итог принята за месяц, нечитаемое стало нулём, выплата со знаком минус
 * уменьшила расходы, сопоставление спрашивают каждый месяц заново.
 */

const START = "2026-01-01";
const empty: Actualization = { actual_until: -1, actuals: {} };

/** Выгрузка «Анализ движения денежных средств» в духе 1С: шапка, группы, итоги. */
const ONE_C: unknown[][] = [
  ["ООО «Ромашка»", null, null, null, null],
  ["Анализ движения денежных средств за 1 квартал 2026 г.", null, null, null, null],
  [null, null, null, null, null],
  ["Статья движения денежных средств", "Январь 2026 г.", "Февраль 2026 г.", "Март 2026 г.", "Итого"],
  ["Поступления", null, null, null, null],
  ["Оплата от покупателей", 1_200_000, 1_350_000, "1 410 000,50", 3_960_000.5],
  ["Выбытия", null, null, null, null],
  ["Оплата поставщикам", -400_000, -420_000, -430_000, -1_250_000],
  ["Аренда", -80_000, -80_000, -80_000, -240_000],
  ["Связь", -5_000, -5_000, "пять тысяч", -15_000],
  ["Заработная плата", -300_000, -300_000, -310_000, -910_000],
  ["Налоги и взносы", -120_000, -95_000, -101_000, -316_000],
  ["Проценты по кредиту", -20_000, -19_000, -18_000, -57_000],
  ["Возврат подотчётных сумм", 3_000, -2_000, null, 1_000],
  ["Итого", 275_000, 432_000, null, null],
];

describe("месяцы в заголовке", () => {
  it("читает разные написания и не путает итог с месяцем", () => {
    expect(monthOf("Январь 2026 г.")).toEqual({ year: 2026, month: 1 });
    expect(monthOf("янв. 26")).toEqual({ year: 2026, month: 1 });
    expect(monthOf("03.2026")).toEqual({ year: 2026, month: 3 });
    expect(monthOf("2026-11")).toEqual({ year: 2026, month: 11 });
    expect(monthOf("М4")).toEqual({ index: 3 });
    expect(monthOf(new Date(2026, 4, 1))).toEqual({ year: 2026, month: 5 });
    expect(monthOf("Итого")).toBeNull();
    expect(monthOf("13.2026")).toBeNull();
  });

  it("шаблон продукта читается обратно тем же разбором", () => {
    const labels = monthLabels("2026-11-01", 3);
    expect(labels).toEqual(["Ноябрь 2026", "Декабрь 2026", "Январь 2027"]);
    const template = buildCashflowTemplate("2026-11-01", 3);
    expect(template[0].map((c) => c.value).slice(1)).toEqual(labels);
    expect(template.slice(1).map((r) => r[0].value)).toEqual(FACT_LINES.map((l) => l.label));
  });
});

describe("разбор выгрузки", () => {
  it("находит заголовок под шапкой, пропускает группы и итоги", () => {
    const sheet = parseCashflowRows(ONE_C, START, 12);
    expect(sheet.error).toBe("");
    expect(sheet.months).toEqual([0, 1, 2]);
    expect(sheet.skippedColumns).toEqual(["«Итого»"]);
    expect(sheet.skippedRows).toEqual(["Итого"]);
    const labels = sheet.articles.map((a) => a.label);
    expect(labels).not.toContain("Поступления");          // группа без чисел — не статья
    expect(labels).toContain("Оплата от покупателей");
  });

  it("месяц вне горизонта назван, а не загружен", () => {
    const sheet = parseCashflowRows([["Статья", "Декабрь 2025", "Январь 2026"],
                                     ["Оплата от покупателей", 1, 2]], START, 12);
    expect(sheet.months).toEqual([0]);
    expect(sheet.skippedColumns).toEqual(["«Декабрь 2025» — вне горизонта модели"]);
  });

  it("числа под колонкой без месяца не пропадают молча", () => {
    const sheet = parseCashflowRows([["Статья", "Январь 2026", null],
                                     ["Оплата поставщикам", 100, 200]], START, 12);
    expect(sheet.skippedColumns[0]).toMatch(/колонка № 3 без месяца/);
  });

  it("лист без месяцев — отказ с объяснением, а не пустой факт", () => {
    expect(parseCashflowRows([["Статья", "Сумма"], ["Аренда", 1]], START, 12).error)
      .toMatch(/месяцами/);
  });
});

describe("сопоставление статей", () => {
  it("сохранённое — раньше подсказки, точное название — раньше подсказки", () => {
    expect(suggest("Оплата от покупателей")).toEqual({ code: "C1", source: "hint" });
    expect(suggest("Налоги")).toEqual({ code: "C12", source: "exact" });
    expect(suggest("Проценты по кредиту")).toEqual({ code: "C24", source: "hint" });
    expect(suggest("Возврат подотчётных сумм")).toEqual({ code: "", source: "none" });
    expect(suggest("Аренда", { [articleKey("аренда ")]: "C11" }))
      .toEqual({ code: "C11", source: "saved" });
    expect(suggest("Аренда", { аренда: "" })).toEqual({ code: "", source: "saved" });
  });
});

describe("наложение на факт", () => {
  const sheet = parseCashflowRows(ONE_C, START, 12);
  const choice = Object.fromEntries(sheet.articles.map((a) => [articleKey(a.label),
                                                              suggest(a.label).code]));
  const { actualization, report } = applyCashflow(empty, sheet, choice, 12);

  it("поступления — как есть, выплаты со знаком минус — по модулю", () => {
    expect(actualization.actuals.C1?.slice(0, 3)).toEqual(["1200000", "1350000", "1410000.5"]);
    expect(actualization.actuals.C2?.slice(0, 3)).toEqual(["400000", "420000", "430000"]);
    expect(report.signs.some((s) => s.includes("Оплата поставщикам"))).toBe(true);
  });

  it("несколько статей на одну строку складываются", () => {
    // Аренда + связь → общие издержки (C5); март связи нечитаем.
    expect(actualization.actuals.C5?.slice(0, 2)).toEqual(["85000", "85000"]);
  });

  it("нечитаемая ячейка не становится нулём: месяц строки не обновлён и назван", () => {
    expect(actualization.actuals.C5?.[2]).toBeNull();
    expect(report.unreadable).toEqual([
      "Общие издержки, М3: в файле нечитаемая ячейка — месяц из файла не обновлён"]);
  });

  it("несопоставленное не загружается и названо; сопоставление запомнено", () => {
    expect(report.ignored).toEqual([{ label: "Возврат подотчётных сумм",
                                      reason: "не сопоставлена со строкой кэш-фло" }]);
    expect(actualization.mapping?.["оплата от покупателей"]).toBe("C1");
    expect(actualization.mapping?.["возврат подотчётных сумм"]).toBe("");
  });

  it("«факт до месяца» сдвигается до последнего загруженного месяца", () => {
    expect(actualization.actual_until).toBe(2);
    expect(report.actualUntil).toBe(2);
  });

  it("статья-выплата с плюсами и минусами не загружается: не понять, что выплата", () => {
    const mixed = applyCashflow(empty, sheet, { ...choice, "возврат подотчётных сумм": "C11" }, 12);
    expect(mixed.report.ignored[0].reason).toMatch(/и плюсы, и минусы/);
    expect(mixed.actualization.actuals.C11).toBeUndefined();
  });

  it("месяцы, которых в файле нет, сохраняют прежний факт", () => {
    const before: Actualization = { actual_until: 5, actuals: { C1: [null, null, null, "7", "8", "9"] } };
    const next = applyCashflow(before, sheet, choice, 12).actualization;
    expect(next.actuals.C1?.slice(0, 6)).toEqual(["1200000", "1350000", "1410000.5", "7", "8", "9"]);
    expect(next.actual_until).toBe(5);
  });
});
