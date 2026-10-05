import { describe, expect, it } from "vitest";
import type { AuditModel, GirboPreview } from "./api/audit";
import { applyGirbo, yearSummary } from "./girboImport";

/**
 * Отчётность из ГИР БО ложится на дело (L3): периоды — годы ресурса, строки — его числа,
 * а всё введённое в деле и привязанное к периодам **переносится по подписи года**. Что не
 * нашло пары — названо, а не обнулено молча.
 */

const preview = (over: Partial<GirboPreview> = {}): GirboPreview => ({
  periods: ["2024", "2025"],
  forms: ["полная", "полная"],
  sources: ["отчётность за 2024 год", "отчётность за 2025 год"],
  balance: { A_FIXED: ["100", "120"], A_CASH: ["10", "20"], P_EQUITY: ["110", "140"] },
  income: { I_REVENUE: ["1000", "1200"], I_COGS: ["600", "700"], I_TAX: ["10", "20"] },
  registry: {
    source: "girbo", fetched_on: "2026-10-04", inn: "2310031475", ogrn: "1022301598549",
    kpp: "231001001", full_name: "АКЦИОНЕРНОЕ ОБЩЕСТВО \"ТАНДЕР\"", short_name: "АО \"ТАНДЕР\"",
    address: "350002, КРАСНОДАР", okved: "47.11 — Торговля", status_code: "ACTIVE",
    status_date: "1996-06-28", periods: ["2024", "2025"], notes: [],
  },
  status_label: "действующая",
  notes: [],
  ...over,
});

const model = (): AuditModel => ({
  name: "Сеть",
  periods: [{ label: "2023", kind: "year" }, { label: "2024", kind: "year" }],
  balance: { A_FIXED: ["1", "2"], M_MARKET_CAP: ["500", "600"] },
  income: { I_REVENUE: ["1", "2"], M_DEPRECIATION: ["7", "8"] },
  revaluations: [{ code: "A_RECEIVABLE", label: "безнадёжная дебиторка", amounts: ["-5", "-9"] }],
  earnings_adjustments: [{ label: "разовый доход", kind: "one_off", amounts: ["0", "-3"] }],
  report: { subject_inn: "", subject_full_name: "Сеть магазинов" },
});

describe("Отчётность из ГИР БО на дело", () => {
  it("заменяет периоды и строки годами и числами ресурса", () => {
    const { model: m } = applyGirbo(model(), preview(), { fillRequisites: false });
    expect(m.periods).toEqual([{ label: "2024", kind: "year" }, { label: "2025", kind: "year" }]);
    expect(m.balance.A_FIXED).toEqual(["100", "120"]);
    expect(m.income.I_REVENUE).toEqual(["1000", "1200"]);
    expect(m.registry?.inn).toBe("2310031475");
  });

  it("переносит введённое по подписи года и называет потерянное", () => {
    const res = applyGirbo(model(), preview(), { fillRequisites: false });
    // 2024 есть в обоих — значения переехали; 2025 нового — нули; 2023 — потерян.
    expect(res.model.balance.M_MARKET_CAP).toEqual(["600", "0"]);
    expect(res.model.income.M_DEPRECIATION).toEqual(["8", "0"]);
    expect(res.model.revaluations?.[0].amounts).toEqual(["-9", "0"]);
    expect(res.model.earnings_adjustments?.[0].amounts).toEqual(["-3", "0"]);
    expect(res.carried).toEqual(expect.arrayContaining(
      ["рыночная капитализация", "амортизация", "переоценка «безнадёжная дебиторка»",
       "нормализация «разовый доход»"]));
    expect(res.dropped).toEqual(expect.arrayContaining(
      ["рыночная капитализация", "амортизация", "переоценка «безнадёжная дебиторка»"]));
    // У нормализации 2023-й был нулём — терять было нечего.
    expect(res.dropped).not.toContain("нормализация «разовый доход»");
  });

  it("заполняет только пустые реквизиты — введённое человеком не перетирается", () => {
    const res = applyGirbo(model(), preview(), { fillRequisites: true });
    expect(res.model.report?.subject_inn).toBe("2310031475");
    expect(res.model.report?.subject_full_name).toBe("Сеть магазинов");
    expect(res.filled).toEqual(["ИНН", "ОГРН", "адрес"]);
    const off = applyGirbo(model(), preview(), { fillRequisites: false });
    expect(off.filled).toEqual([]);
    expect(off.model.report?.subject_inn).toBe("");
  });

  it("сводка года — выручка, чистая прибыль и итог баланса", () => {
    expect(yearSummary(preview(), 1)).toEqual({ revenue: 1200, net: 480, assets: 140 });
  });
});
