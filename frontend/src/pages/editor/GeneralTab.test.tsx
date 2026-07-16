// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Environment, ProjectHeader, ProjectSettings } from "../../api/model";
import { GeneralTab } from "./GeneralTab";

afterEach(cleanup);

const header = { name: "П", start_date: "2026-01-01", duration_months: 12 } as ProjectHeader;
const settings = { profit_tax_rate: "0.20", vat_rate: "0.20",
                   discount_rate_annual: "0.15" } as unknown as ProjectSettings;

function renderTab(environment: Environment, onEnvironment = vi.fn()) {
  render(
    <GeneralTab header={header} settings={settings} environment={environment}
                onHeader={vi.fn()} onSettings={vi.fn()} onEnvironment={onEnvironment} />,
  );
  return onEnvironment;
}

describe("GeneralTab — настраиваемые налоги", () => {
  it("добавляет налог с дефолтами", () => {
    const onEnv = renderTab({ fx_open: "1", fx_rate: [] });
    fireEvent.click(screen.getByText(/Добавить налог/));
    expect(onEnv).toHaveBeenCalledWith({
      fx_open: "1", fx_rate: [],
      taxes: [{ name: "Налог 1", rate: "0", base: "revenue", formula: "",
                periodicity: "month", allocation: "expense" }],
    });
  });

  it("показывает поле формулы только при base=formula", () => {
    renderTab({ fx_open: "1", fx_rate: [],
                taxes: [{ name: "Т", rate: "0.01", base: "formula", formula: "МАКС(C13, 0)",
                          periodicity: "month", allocation: "expense" }] });
    expect(screen.getByDisplayValue("МАКС(C13, 0)")).toBeTruthy();
    cleanup();
    renderTab({ fx_open: "1", fx_rate: [],
                taxes: [{ name: "Т", rate: "0.01", base: "revenue", formula: "",
                          periodicity: "month", allocation: "expense" }] });
    expect(screen.queryByText("Формула базы")).toBeNull();
  });

  it("удаляет налог", () => {
    const onEnv = renderTab({ fx_open: "1", fx_rate: [],
                              taxes: [{ name: "Т", rate: "0", base: "revenue", formula: "",
                                        periodicity: "month", allocation: "expense" }] });
    fireEvent.click(screen.getByTitle("Удалить налог"));
    expect(onEnv).toHaveBeenCalledWith({ fx_open: "1", fx_rate: [], taxes: [] });
  });
});
