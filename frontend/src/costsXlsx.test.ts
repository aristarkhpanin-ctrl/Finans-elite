import { describe, expect, it } from "vitest";
import type { OperatingPlan } from "./api/model";
import {
  applyCostsWorkbook,
  buildCostsWorkbook,
  DEFAULTS,
  SHEET_DIRECT,
  SHEET_FIXED,
  SHEET_STAFF,
} from "./costsXlsx";
import { cellNumber, cellSeries } from "./xlsxCells";

/**
 * Импорт издержек и персонала (G13). Проверяются обещания отчёта: найденное обновляется,
 * недостающее создаётся **отдельным списком с названными умолчаниями**, нечитаемое не
 * становится нулём, повторы и отсутствующие листы названы, чужие поля статьи целы.
 */

const plan = (): OperatingPlan => ({
  products: [],
  sales: [],
  production: [],
  direct_costs: [
    { name: "Мука", kind: "materials", amount: ["100", "120"], payment_delay_months: 2,
      stock_lead_months: 1 },
  ],
  fixed_costs: [
    { name: "Аренда", function: "admin", amount: ["50", "50"], payment_delay_months: 1,
      from_profit: false },
  ],
  staff: [
    { name: "Пекарь", monthly_salary: "60000", headcount: "2", start_month: 0,
      end_month: null, function: "staff_production", payment_delay_months: 1 },
  ],
});

/** Книга как её вернёт read-excel-file: значения ячеек по листам. */
function roundTrip(p: OperatingPlan, n: number): Record<string, unknown[][]> {
  const out: Record<string, unknown[][]> = {};
  for (const s of buildCostsWorkbook(p, n)) out[s.sheet] = s.data.map((r) => r.map((c) => c.value));
  return out;
}

describe("Разбор ячеек", () => {
  it("русское написание читается, нечитаемое — не ноль", () => {
    expect(cellNumber("1 200,50")).toBe(1200.5);
    expect(cellNumber("5,0")).toBe(5);
    expect(cellNumber(42)).toBe(42);
    expect(cellNumber("")).toBeUndefined();
    expect(cellNumber(null)).toBeUndefined();
    expect(Number.isNaN(cellNumber("сто"))).toBe(true);
    expect(Number.isNaN(cellNumber("1 2"))).toBe(true);        // не угадываем двенадцать
    expect(Number.isNaN(cellNumber(true))).toBe(true);
  });

  it("ряд: пусто — ноль, нечитаемое — ошибка с номером месяца", () => {
    expect(cellSeries([1, "", null], 3)).toEqual({ values: ["1", "0", "0"] });
    expect(cellSeries([1, "два"], 2)).toEqual({ error: "М2: «два» — не число" });
  });
});

describe("Книга издержек", () => {
  it("round-trip: шаблон → книга → та же модель", () => {
    const p = plan();
    const res = applyCostsWorkbook(p, roundTrip(p, 2), 2);
    expect(res.operating.direct_costs).toEqual(p.direct_costs);
    expect(res.operating.fixed_costs).toEqual(p.fixed_costs);
    expect(res.operating.staff).toEqual(p.staff);
    expect(res.sheets.flatMap((s) => s.problems)).toEqual([]);
  });

  it("найденное обновляется по имени, чужие поля статьи целы", () => {
    const res = applyCostsWorkbook(plan(), {
      [SHEET_DIRECT]: [["Статья", "Вид", "М1", "М2"], ["  мука ", "Материалы", 110, "1 300,5"]],
    }, 2);
    const flour = res.operating.direct_costs[0];
    expect(flour.amount).toEqual(["110", "1300.5"]);
    expect(flour.payment_delay_months).toBe(2);                  // отсрочка из модели цела
    expect(flour.name).toBe("Мука");                             // имя модели, не файла
    expect(res.sheets[0].updated).toEqual(["Мука"]);
  });

  it("недостающее создаётся — отдельно и с названными умолчаниями", () => {
    const res = applyCostsWorkbook(plan(), {
      [SHEET_FIXED]: [["Связь", "", 5, 5]],
      [SHEET_STAFF]: [["Кассир", 40000]],
    }, 2);
    const fixed = res.sheets.find((s) => s.sheet === SHEET_FIXED)!;
    expect(fixed.created).toEqual(["Связь"]);
    expect(fixed.defaults).toBe(DEFAULTS[SHEET_FIXED]);
    expect(res.operating.fixed_costs[1]).toEqual(
      { name: "Связь", function: "admin", amount: ["5", "5"], payment_delay_months: 0 });
    expect(res.operating.staff?.[1]).toEqual({
      name: "Кассир", monthly_salary: "40000", headcount: "1", start_month: 0,
      end_month: null, function: "staff_admin" });
    expect(DEFAULTS[SHEET_STAFF]).toMatch(/численность — 1/);
  });

  it("нечитаемое не становится нулём: строка не применяется, место названо", () => {
    const p = plan();
    const res = applyCostsWorkbook(p, {
      [SHEET_DIRECT]: [["Статья", "Вид", "М1", "М2"], ["Мука", "Материалы", 110, "сто"]],
    }, 2);
    expect(res.operating.direct_costs[0].amount).toEqual(["100", "120"]);   // как было
    expect(res.sheets[0].problems).toEqual(
      ["строка 2 («Мука»): М2: «сто» — не число — строка не применена"]);
    expect(res.changed).toBe(false);
    expect(res.operating).toBe(p);
  });

  it("неизвестный вид и функция названы с подсказкой", () => {
    const res = applyCostsWorkbook(plan(), {
      [SHEET_DIRECT]: [["Сахар", "Сырьё", 1, 1]],
      [SHEET_STAFF]: [["Курьер", 30000, 1, 1, "", "Логистический"]],
    }, 2);
    expect(res.sheets[0].problems[0]).toMatch(/«Материалы» или «Сдельная оплата»/);
    expect(res.sheets[2].problems[0]).toMatch(/«Административный»/);
  });

  it("персонал: месяцы от единицы ↔ модель от нуля, пусто — до конца горизонта", () => {
    const res = applyCostsWorkbook(plan(), {
      [SHEET_STAFF]: [["Пекарь", 65000, 3, 4, 12, "Производственный"]],
    }, 24);
    expect(res.operating.staff?.[0]).toMatchObject(
      { monthly_salary: "65000", headcount: "3", start_month: 3, end_month: 12,
        function: "staff_production", payment_delay_months: 1 });
    const bad = applyCostsWorkbook(plan(), { [SHEET_STAFF]: [["Пекарь", 65000, 1, 5, 2]] }, 24);
    expect(bad.sheets[2].problems[0]).toMatch(/не раньше первого/);
    const noSalary = applyCostsWorkbook(plan(), { [SHEET_STAFF]: [["Пекарь", ""]] }, 24);
    expect(noSalary.sheets[2].problems[0]).toMatch(/не задан оклад/);
  });

  it("повтор имени в файле — взята первая строка, повтор назван", () => {
    const res = applyCostsWorkbook(plan(), {
      [SHEET_FIXED]: [["Аренда", "Административные", 70, 70], ["аренда", "", 1, 1]],
    }, 2);
    expect(res.operating.fixed_costs[0].amount).toEqual(["70", "70"]);
    expect(res.sheets[1].problems[0]).toMatch(/уже была выше — взята первая/);
  });

  it("листа нет — раздел не тронут, и это сказано", () => {
    const p = plan();
    const res = applyCostsWorkbook(p, { [SHEET_STAFF]: [["Пекарь", 61000, 2]] }, 2);
    expect(res.sheets.find((s) => s.sheet === SHEET_DIRECT)?.absent).toBe(true);
    expect(res.operating.direct_costs).toBe(p.direct_costs);
    expect(res.sheets.find((s) => s.sheet === SHEET_STAFF)?.absent).toBe(false);
  });

  it("статьи модели, которых нет в файле, не удаляются", () => {
    const res = applyCostsWorkbook(plan(), { [SHEET_DIRECT]: [["Соль", "", 1, 1]] }, 2);
    expect(res.operating.direct_costs.map((d) => d.name)).toEqual(["Мука", "Соль"]);
  });

  it("шаблон: ряд короче горизонта дополнен нулями, пустой раздел — только заголовок", () => {
    const empty: OperatingPlan = { ...plan(), direct_costs: [], staff: [] };
    const book = buildCostsWorkbook(empty, 3);
    expect(book.map((s) => s.sheet)).toEqual([SHEET_DIRECT, SHEET_FIXED, SHEET_STAFF]);
    expect(book[0].data).toHaveLength(1);
    expect(book[1].data[1].slice(2).map((c) => c.value)).toEqual([50, 50, 0]);
  });
});
