// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DebtServiceView } from "./DebtServiceView";

/**
 * Взгляд банка (пакет L, L1): покрытие долга по годам, оценка **словами** (не только
 * цветом), недостаток покрытия и причины пустых клеток. Оговорка — с сервера.
 */

afterEach(cleanup);

const year = (over: Record<string, unknown>) => ({
  label: "Год 1", start: 0, months: 12, cfads: "900000", interest: "100000",
  principal: "900000", lease: "0", service: "1000000", dscr: "0.9", shortfall: "100000",
  net_debt: "5000000", ebitda: "1000000", leverage: "5", leverage_note: "", ...over,
});

const debt = {
  min_dscr: "0.9",
  min_dscr_year: "Год 1",
  note: "Покрытие долга (DSCR) — поток к платежам. Это практика, а не норма закона.",
  years: [
    year({}),
    year({ label: "Год 2", cfads: "1150000", dscr: "1.15", shortfall: "0", leverage: "3" }),
    year({ label: "Год 3", cfads: "2000000", dscr: "2", shortfall: "0", leverage: "1" }),
    year({ label: "Год 4", months: 6, service: "0", principal: "0", interest: "0",
           dscr: null, shortfall: "0", leverage: null,
           leverage_note: "неполный год: годовой EBITDA нет" }),
  ],
};

describe("Взгляд банка на сводке", () => {
  it("называет покрытие словами, недостаток и пустые клетки — с причиной", () => {
    render(<DebtServiceView debt={debt} />);
    expect(screen.getByRole("heading", { name: "Обслуживание долга (взгляд банка)" })).toBeTruthy();
    expect(screen.getByText("не покрывает платежи")).toBeTruthy();
    expect(screen.getByText("ниже требования банков")).toBeTruthy();
    expect(screen.getByText("с запасом")).toBeTruthy();
    expect(screen.getByText("платежей нет")).toBeTruthy();
    expect(document.body.textContent).toContain("Год 4 (6 мес.)");
    expect(document.body.textContent).toContain("Год 1: не хватает 0,10");
    expect(document.body.textContent).toContain("Год 4 — неполный год: годовой EBITDA нет");
    expect(screen.getByText(debt.note)).toBeTruthy();
    expect(screen.getByRole("region", { name: "Обслуживание долга по годам" })).toBeTruthy();
  });

  it("без долга блока нет", () => {
    const { container } = render(<DebtServiceView debt={null} />);
    expect(container.textContent).toBe("");
  });
});
