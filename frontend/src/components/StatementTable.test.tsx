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
    <StatementTable statement={statement} n={2} subtotals={new Set(["I4"])}
                    details={withDetails ? details : undefined} />,
  );
}

describe("StatementTable drill-down", () => {
  it("метки колонок по умолчанию — М1…Мn; кастомные labels применяются", () => {
    render(<StatementTable statement={statement} n={2} subtotals={new Set()}
                           labels={["Год 1", "Год 2"]} />);
    expect(screen.getByText("Год 1")).toBeTruthy();
    expect(screen.queryByText("М1")).toBeNull();
  });

  it("строка с детализацией раскрывается в слагаемые и сворачивается", () => {
    renderTable();
    expect(screen.queryByText("Стул")).toBeNull();               // свёрнуто по умолчанию
    fireEvent.click(screen.getByTitle("Раскрыть слагаемые"));
    expect(screen.getByText("Стул")).toBeTruthy();
    expect(screen.getByText("Стол")).toBeTruthy();
    fireEvent.click(screen.getByTitle("Раскрыть слагаемые"));
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
