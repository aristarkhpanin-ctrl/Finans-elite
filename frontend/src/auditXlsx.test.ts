import { describe, expect, it } from "vitest";
import type { AuditModel } from "./api/audit";
import { applyAuditRows, buildAuditTemplate } from "./auditXlsx";

const model = (): AuditModel => ({
  name: "ООО «Пример»",
  currency: "RUB",
  industry: "Торговля",
  periods: [{ label: "2023", kind: "year" }, { label: "2024", kind: "year" }],
  balance: { A_CASH: ["30", "50"], P_EQUITY: ["120", "150"] },
  income: { I_REVENUE: ["500", "600"] },
});

const values = (rows: (string | number | null)[][], code: string) =>
  rows.find((r) => r[0] === code)!.slice(2);

describe("buildAuditTemplate", () => {
  it("заголовок + разделы + строки каталога по периодам", () => {
    const rows = buildAuditTemplate(model()).map((r) => r.map((c) => c.value));
    expect(rows[0]).toEqual(["Код", "Статья", "2023", "2024"]);
    expect(rows.some((r) => r[1] === "БАЛАНС — АКТИВ")).toBe(true);
    expect(rows.some((r) => r[1] === "ОТЧЁТ О ФИНАНСОВЫХ РЕЗУЛЬТАТАХ")).toBe(true);
    // введённые значения переносятся, незаполненные строки — нули
    expect(values(rows, "A_CASH")).toEqual([30, 50]);
    expect(values(rows, "I_REVENUE")).toEqual([500, 600]);
    expect(values(rows, "A_FIXED")).toEqual([0, 0]);
  });

  it("включает служебные строки расшифровки (диагностика без них не считается)", () => {
    const rows = buildAuditTemplate(model()).map((r) => r.map((c) => c.value));
    expect(rows.some((r) => r[0] === "M_RETAINED")).toBe(true);
    expect(rows.some((r) => r[0] === "M_MARKET_CAP")).toBe(true);
  });

  it("рыночная капитализация переносится через шаблон в модель", () => {
    const m = { ...model(), balance: { ...model().balance, M_MARKET_CAP: ["1200", "1500"] } };
    const tpl = buildAuditTemplate(m).map((r) => r.map((c) => c.value));
    const res = applyAuditRows(m, tpl as (string | number)[][]);
    expect(res.model.balance.M_MARKET_CAP).toEqual(["1200", "1500"]);
  });
});

describe("applyAuditRows", () => {
  it("round-trip: шаблон → импорт → те же значения", () => {
    const m = model();
    const tpl = buildAuditTemplate(m).map((r) => r.map((c) => c.value));
    const res = applyAuditRows(m, tpl as (string | number)[][]);
    expect(res.skipped).toEqual([]);
    expect(res.model.balance.A_CASH).toEqual(["30", "50"]);
    expect(res.model.income.I_REVENUE).toEqual(["500", "600"]);
  });

  it("матч по коду обновляет нужную таблицу модели", () => {
    const res = applyAuditRows(model(), [
      ["A_FIXED", "Внеоборотные активы", 100, 120],
      ["I_COGS", "Себестоимость продаж", 300, 360],
    ]);
    expect(res.matched).toBe(2);
    expect(res.model.balance.A_FIXED).toEqual(["100", "120"]);
    expect(res.model.income.I_COGS).toEqual(["300", "360"]);
    // прочие значения не затронуты
    expect(res.model.balance.A_CASH).toEqual(["30", "50"]);
  });

  it("матч по названию статьи, если код не указан", () => {
    const res = applyAuditRows(model(), [["", "  запасы ", 40, 45]]);
    expect(res.matched).toBe(1);
    expect(res.model.balance.A_INVENTORY).toEqual(["40", "45"]);
  });

  it("нормализует запятую, пробелы-разряды и пустые ячейки", () => {
    const res = applyAuditRows(model(), [["A_CASH", "Денежные средства", "1 234,5", null]]);
    expect(res.model.balance.A_CASH).toEqual(["1234.5", "0"]);
  });

  it("приводит ряд к числу периодов", () => {
    const long = applyAuditRows(model(), [["A_CASH", "", 1, 2, 3, 4]]);
    expect(long.model.balance.A_CASH).toEqual(["1", "2"]);
    const short = applyAuditRows(model(), [["A_CASH", "", 7]]);
    expect(short.model.balance.A_CASH).toEqual(["7", "0"]);
  });

  it("служебные строки игнорируются, неизвестные — в skipped", () => {
    const res = applyAuditRows(model(), [
      ["Код", "Статья", "2023", "2024"],
      ["", "БАЛАНС — АКТИВ", "", ""],
      ["X_UNKNOWN", "Что-то своё", 1, 2],
      ["A_CASH", "Денежные средства", 9, 9],
    ]);
    expect(res.ignored).toBe(2);
    expect(res.skipped).toEqual(["X_UNKNOWN"]);
    expect(res.matched).toBe(1);
    expect(res.model.balance.A_CASH).toEqual(["9", "9"]);
  });

  it("периоды и реквизиты субъекта импорт не меняет", () => {
    const m = model();
    const res = applyAuditRows(m, [["A_CASH", "", 1, 2]]);
    expect(res.model.periods).toEqual(m.periods);
    expect(res.model.name).toBe(m.name);
    expect(res.model.currency).toBe(m.currency);
  });

  it("ничего не сопоставлено → модель возвращается той же ссылкой", () => {
    const m = model();
    const res = applyAuditRows(m, [["X", "чужое", 1]]);
    expect(res.matched).toBe(0);
    expect(res.model).toBe(m);
  });
});
