import { describe, expect, it } from "vitest";
import type { OperatingPlan, SalesLine } from "./api/model";
import { ROW_PRICE, ROW_VOLUME, applySalesRows, buildSalesTemplate } from "./salesXlsx";

const line = (product_id: string, volume: string[], price: string[]): SalesLine => ({
  product_id, volume, price, payment: { prepayment_share: "0", advance_lead_months: 0, payment_delay_months: 0 },
});

const plan = (): OperatingPlan => ({
  products: [
    { id: "a", name: "Хлеб" },
    { id: "b", name: "Молоко" },
  ],
  sales: [line("a", ["10", "10"], ["50", "50"]), line("b", ["5", "5"], ["80", "80"])],
  production: [],
  direct_costs: [],
  fixed_costs: [],
});

describe("buildSalesTemplate", () => {
  it("заголовок + два ряда на продукт, длина = горизонт", () => {
    const rows = buildSalesTemplate(plan(), 2);
    expect(rows[0].map((c) => c.value)).toEqual(["Продукт", "Показатель", "М1", "М2"]);
    expect(rows).toHaveLength(1 + 2 * 2); // header + (объём+цена)×2 продукта
    // объём — числовые ячейки
    const bread = rows[1];
    expect(bread[0].value).toBe("Хлеб");
    expect(bread[1].value).toBe(ROW_VOLUME);
    expect(bread.slice(2).map((c) => c.value)).toEqual([10, 10]);
  });

  it("дополняет короткий ряд нулями до горизонта", () => {
    const rows = buildSalesTemplate(plan(), 4);
    expect(rows[1].slice(2).map((c) => c.value)).toEqual([10, 10, 0, 0]);
  });
});

describe("applySalesRows", () => {
  it("round-trip: шаблон → строки → те же ряды", () => {
    const p = plan();
    const tpl = buildSalesTemplate(p, 2).map((r) => r.map((c) => c.value));
    const res = applySalesRows(p, tpl as (string | number)[][], 2);
    expect(res.matched).toBe(2);
    expect(res.skipped).toEqual([]);
    expect(res.operating.sales[0].volume).toEqual(["10", "10"]);
    expect(res.operating.sales[1].price).toEqual(["80", "80"]);
  });

  it("сопоставляет продукт по имени без учёта регистра/пробелов и обновляет значения", () => {
    const res = applySalesRows(plan(), [
      ["Продукт", "Показатель", "М1", "М2"],
      ["  хлеб ", "Объём", 20, 30],
      ["Хлеб", "Цена", 55, 60],
    ], 2);
    expect(res.matched).toBe(1);
    expect(res.operating.sales[0].volume).toEqual(["20", "30"]);
    expect(res.operating.sales[0].price).toEqual(["55", "60"]);
    // молоко не тронуто
    expect(res.operating.sales[1].volume).toEqual(["5", "5"]);
  });

  it("нормализует запятую-десятичную и пустые ячейки", () => {
    const res = applySalesRows(plan(), [["Молоко", "Цена", "80,5", null]], 2);
    expect(res.operating.sales[1].price).toEqual(["80.5", "0"]);
  });

  it("обрезает/дополняет ряд под горизонт", () => {
    const long = applySalesRows(plan(), [["Хлеб", "Объём", 1, 2, 3, 4]], 2);
    expect(long.operating.sales[0].volume).toEqual(["1", "2"]);
    const short = applySalesRows(plan(), [["Хлеб", "Объём", 7]], 3);
    expect(short.operating.sales[0].volume).toEqual(["7", "0", "0"]);
  });

  it("неизвестный продукт → skipped, модель без изменений", () => {
    const p = plan();
    const res = applySalesRows(p, [["Сыр", "Объём", 1, 2]], 2);
    expect(res.matched).toBe(0);
    expect(res.skipped).toEqual(["Сыр"]);
    expect(res.operating).toBe(p); // ссылка не меняется, если ничего не сопоставлено
  });

  it("нераспознанный показатель → ignored, не влияет на модель", () => {
    const res = applySalesRows(plan(), [
      ["Хлеб", "Себестоимость", 1, 2],
      ["Хлеб", ROW_PRICE, 9, 9],
    ], 2);
    expect(res.ignored).toBe(1);
    expect(res.matched).toBe(1);
    expect(res.operating.sales[0].price).toEqual(["9", "9"]);
    expect(res.operating.sales[0].volume).toEqual(["10", "10"]); // объём не тронут
  });

  it("пропускает строку заголовка", () => {
    const res = applySalesRows(plan(), [
      ["Продукт", "Показатель", "М1", "М2"],
      ["Хлеб", "Объём", 3, 3],
    ], 2);
    expect(res.ignored).toBe(0);
    expect(res.matched).toBe(1);
  });
});
