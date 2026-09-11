// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { AuditInputIssue } from "../api/audit";
import { AuditInputIssues } from "./AuditInputIssues";

afterEach(cleanup);

function issue(over: Partial<AuditInputIssue> = {}): AuditInputIssue {
  return {
    code: "balance_gap", severity: "error", title: "Актив не равен пассиву",
    detail: "Расхождение в периодах: 2024 — -849.",
    periods: [1], evidence: { max_gap: "-849" }, ...over,
  };
}

const PERIODS = ["2023", "2024"];

describe("Панель качества данных", () => {
  it("на чистом вводе панели нет вовсе", () => {
    // Плашка «проблем не найдено» занимала бы внимание, которого на экране с
    // числами и так мало, и не сообщала бы ничего сверх пустого места.
    const { container } = render(<AuditInputIssues issues={[]} periods={PERIODS} />);
    expect(container.firstChild).toBeNull();
  });

  it("находка названа, объяснена и привязана к периодам", () => {
    render(<AuditInputIssues issues={[issue()]} periods={PERIODS} />);
    expect(screen.getByText("Актив не равен пассиву")).toBeTruthy();
    expect(screen.getByText(/Расхождение в периодах/)).toBeTruthy();
    // период назван так же, как в таблицах, а не индексом
    expect(screen.getByText("2024")).toBeTruthy();
  });

  it("период без подписи назван по номеру, а не пустотой", () => {
    render(<AuditInputIssues issues={[issue({ periods: [5] })]} periods={PERIODS} />);
    expect(screen.getByText("Период 6")).toBeTruthy();
  });

  it("находка на всю модель периодов не показывает", () => {
    render(<AuditInputIssues issues={[issue({ code: "no_income", periods: [] })]}
                             periods={PERIODS} />);
    expect(screen.queryByText("2023")).toBeNull();
    expect(screen.queryByText("2024")).toBeNull();
  });

  it("тяжесть видна словом, а не только цветом", () => {
    // Цвет — усиление, а не единственный носитель смысла (правило хендоффа §7d).
    render(<AuditInputIssues periods={PERIODS} issues={[
      issue({ severity: "error" }),
      issue({ code: "empty_period", severity: "warning", title: "Период без данных" }),
      issue({ code: "blank_period_label", severity: "info", title: "Период без подписи" }),
    ]} />);
    expect(screen.getByText("Ошибка")).toBeTruthy();
    expect(screen.getByText("Внимание")).toBeTruthy();
    expect(screen.getByText("Замечание")).toBeTruthy();
  });

  it("заголовок считает находки по весу", () => {
    render(<AuditInputIssues periods={PERIODS} issues={[
      issue(), issue({ code: "negative_line" }),
      issue({ code: "empty_period", severity: "warning" }),
    ]} />);
    expect(screen.getByText("2 ошибок в данных · 1 предупреждений")).toBeTruthy();
  });
});
