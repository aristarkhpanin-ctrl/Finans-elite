// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { StatementOut } from "../api/calc";
import { StatementTable, type DetailRow } from "./StatementTable";

afterEach(cleanup);

const statement: StatementOut = {
  lines: [
    { code: "I1", label: "Валовый объём продаж", values: ["300", "300"] },
    { code: "I4", label: "Чистый объём продаж", values: ["300", "300"] },
  ],
};

const details = new Map<string, DetailRow[]>([
  ["I1", [
    { name: "Стул", values: ["100", "100"] },
    { name: "Стол", values: ["200", "200"] },
  ]],
]);

function renderTable(withDetails = true) {
  return render(
    <StatementTable title="Отчёт о прибылях" statement={statement} n={2} subtotals={new Set(["I4"])}
                    details={withDetails ? details : undefined} />,
  );
}

describe("StatementTable drill-down", () => {
  it("метки колонок по умолчанию — М1…Мn; кастомные labels применяются", () => {
    render(<StatementTable title="Отчёт о прибылях" statement={statement} n={2} subtotals={new Set()}
                           labels={["Год 1", "Год 2"]} />);
    expect(screen.getByText("Год 1")).toBeTruthy();
    expect(screen.queryByText("М1")).toBeNull();
  });

  it("строка с детализацией раскрывается в слагаемые и сворачивается", () => {
    renderTable();
    expect(screen.queryByText("Стул")).toBeNull();               // свёрнуто по умолчанию
    // Раскрываемая строка — кнопка с состоянием (пакет K, K5): до неё доходят Tab и
    // диктор, а не только мышь, и раскрытость названа, а не нарисована стрелкой.
    const row = screen.getByTitle("Раскрыть слагаемые");
    expect(row.tagName).toBe("BUTTON");
    expect(row.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(row);
    expect(screen.getByText("Стул")).toBeTruthy();
    expect(screen.getByText("Стол")).toBeTruthy();
    expect(row.getAttribute("aria-expanded")).toBe("true");
    expect(row.getAttribute("title")).toBe("Свернуть слагаемые");
    fireEvent.click(row);
    expect(screen.queryByText("Стул")).toBeNull();
  });

  it("строки без детализации не кликабельны, легенда только при details", () => {
    renderTable(false);
    expect(screen.queryByTitle("Раскрыть слагаемые")).toBeNull();
    expect(screen.queryByText(/раскрывается в слагаемые/)).toBeNull();
    cleanup();
    renderTable();
    expect(screen.getByText(/раскрывается в слагаемые/)).toBeTruthy();
  });
});

describe("StatementTable с клавиатуры (H6)", () => {
  it("таблица шире экрана — область с именем, до которой доходит Tab", () => {
    // Без tabIndex прокрутить стрелками нельзя: в таблице без детализации нажимать нечего.
    renderTable(false);
    const region = screen.getByRole("region", { name: "Отчёт о прибылях" });
    expect(region.tabIndex).toBe(0);
  });
});
