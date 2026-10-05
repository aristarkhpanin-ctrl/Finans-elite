// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Actualization } from "../../api/model";
import type { CalcResponse } from "../../api/calc";

/**
 * Вкладка «Факт» (L7): пустая ячейка — «факта нет», а не ноль; перерасход по выплате —
 * хуже плана, а не лучше; файл ДДС ложится на строки кэш-фло после того, как человек
 * увидел сопоставление.
 */

const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));
const readCashflowXlsx = vi.fn();
vi.mock("../../cashflowXlsx", async (orig) => ({
  ...(await orig<typeof import("../../cashflowXlsx")>()),
  readCashflowXlsx: (f: unknown) => readCashflowXlsx(f),
}));

const { ActualizationTab, better } = await import("./ActualizationTab");

const plan = {
  cashflow: { lines: [
    { code: "C1", label: "Поступления от продаж", values: ["1000", "1000", "1000"] },
    { code: "C6", label: "Затраты на персонал", values: ["500", "500", "500"] },
  ] },
} as unknown as CalcResponse;

function show(actualization: Actualization, onChange = vi.fn()) {
  const qc = new QueryClient();
  qc.setQueryData(["calc", "p1"], plan);
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route path="/projects/:id" element={
            <ActualizationTab n={3} start="2026-01-01" actualization={actualization}
                              onChange={onChange} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onChange;
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("ввод факта", () => {
  it("стёртая ячейка — «факта нет» (null), а не пустая строка и не ноль", () => {
    const onChange = show({ actual_until: 1, actuals: { C1: ["900", "950", null] } });
    fireEvent.change(screen.getByTitle("Поступления от продаж · М2"), { target: { value: "" } });
    expect(onChange).toHaveBeenCalledWith({ actual_until: 1, actuals: { C1: ["900", null, null] } });
  });

  it("лучше плана — по знаку статьи: перерасход по выплате красный", () => {
    expect(better(100, true)).toBe(true);     // поступлений больше плана — хорошо
    expect(better(100, false)).toBe(false);   // зарплаты больше плана — плохо
    expect(better(-100, false)).toBe(true);
  });

  it("строка с фактом видна, даже если её нет среди основных", () => {
    show({ actual_until: 0, actuals: { C24: ["20000", null, null] } });
    expect(screen.getByText("Выплаты процентов по займам")).toBeTruthy();
  });
});

describe("факт ДДС из файла", () => {
  it("сопоставление видно до загрузки, загрузка сохраняет и его", async () => {
    readCashflowXlsx.mockResolvedValue([
      ["Статья", "Январь 2026", "Февраль 2026"],
      ["Оплата от покупателей", 1200, 1300],
      ["Заработная плата", -500, -510],
      ["Возврат подотчётных сумм", 10, null],
    ]);
    const onChange = show({ actual_until: 0, actuals: {} });
    const input = screen.getByLabelText("Файл с фактом ДДС") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "ddc.xlsx")] } });

    const dialog = await screen.findByRole("dialog", { name: "Факт ДДС из файла" });
    expect(within(dialog).getByLabelText("Оплата от покупателей")).toHaveProperty("value", "C1");
    expect(within(dialog).getByLabelText("Заработная плата")).toHaveProperty("value", "C6");
    expect(within(dialog).getByText("не сопоставлена")).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: "Загрузить факт" }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const next = onChange.mock.calls[0][0] as Actualization;
    expect(next.actuals.C1?.slice(0, 2)).toEqual(["1200", "1300"]);
    expect(next.actuals.C6?.slice(0, 2)).toEqual(["500", "510"]);
    expect(next.actual_until).toBe(1);
    expect(next.mapping?.["возврат подотчётных сумм"]).toBe("");
    expect(within(dialog).getByText(/«Возврат подотчётных сумм» не загружена/)).toBeTruthy();
  });

  it("файл без месяцев — отказ с объяснением, окна нет", async () => {
    readCashflowXlsx.mockResolvedValue([["Статья", "Сумма"], ["Аренда", 1]]);
    show({ actual_until: 0, actuals: {} });
    fireEvent.change(screen.getByLabelText("Файл с фактом ДДС"),
                     { target: { files: [new File(["x"], "a.xlsx")] } });
    await waitFor(() => expect(toast).toHaveBeenCalledWith("Файл не разобран",
      expect.objectContaining({ kind: "warn" })));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
