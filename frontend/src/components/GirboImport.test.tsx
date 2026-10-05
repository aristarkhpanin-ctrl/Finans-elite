// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuditModel, GirboPreview } from "../api/audit";

/**
 * Окно «Отчётность по ИНН» (L3): до замены видно, чья отчётность, действует ли
 * организация, какие годы и что куда отнесено; отказ сервера — его словами.
 */

const getGirboPreview = vi.fn();
vi.mock("../api/audit", async (orig) => ({
  ...(await orig<typeof import("../api/audit")>()),
  getGirboPreview: (inn: string) => getGirboPreview(inn),
}));

const { GirboImport } = await import("./GirboImport");

const preview: GirboPreview = {
  periods: ["2024", "2025"], forms: ["полная", "упрощённая"],
  sources: ["отчётность за 2024 год", "отчётность за 2025 год"],
  balance: { A_CASH: ["10000000", "20000000"], P_EQUITY: ["10000000", "20000000"] },
  income: { I_REVENUE: ["100000000", "120000000"] },
  registry: {
    source: "girbo", fetched_on: "2026-10-04", inn: "2310031475", ogrn: "1022301598549",
    kpp: "", full_name: "ООО «ЦЕЛЬ»", short_name: "ООО «ЦЕЛЬ»", address: "", okved: "",
    status_code: "INACTIVE", status_date: "2026-03-31", periods: ["2024", "2025"], notes: [],
  },
  status_label: "недействующая",
  notes: ["Суммы в ресурсе — в тысячах рублей; в деле — в рублях (×1000)."],
};

const model: AuditModel = { periods: [], balance: {}, income: {} };

function show(onApply = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <GirboImport open onClose={vi.fn()} model={model} onApply={onApply} />
    </QueryClientProvider>,
  );
  return onApply;
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("Отчётность по ИНН из ГИР БО", () => {
  it("показывает чьё, какой статус и какие годы — до замены", async () => {
    getGirboPreview.mockResolvedValue(preview);
    const onApply = show();
    const replace = screen.getByRole("button", { name: "Заменить отчётность дела" });
    expect((replace as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("ИНН организации"), { target: { value: "2310031475" } });
    fireEvent.click(screen.getByRole("button", { name: "Найти" }));
    await screen.findByText("ООО «ЦЕЛЬ»");
    expect(getGirboPreview).toHaveBeenCalledWith("2310031475");
    expect(document.body.textContent).toContain("Статус: недействующая с 31.03.2026");
    expect(document.body.textContent).toContain("станет флагом риска");
    expect(screen.getByText("упрощённая")).toBeTruthy();
    expect(screen.getByText(/в тысячах рублей/)).toBeTruthy();
    fireEvent.click(replace);
    await waitFor(() => expect(onApply).toHaveBeenCalledTimes(1));
    expect(onApply.mock.calls[0][0].model.periods).toHaveLength(2);
  });

  it("отказ сервера — его словами", async () => {
    getGirboPreview.mockRejectedValue({
      isAxiosError: true,
      response: { status: 404, data: { detail: "Организации с ИНН 2310031475 в ГИР БО нет" } },
    });
    show();
    fireEvent.change(screen.getByLabelText("ИНН организации"), { target: { value: "2310031475" } });
    fireEvent.click(screen.getByRole("button", { name: "Найти" }));
    expect((await screen.findByRole("alert")).textContent).toContain("в ГИР БО нет");
  });
});
