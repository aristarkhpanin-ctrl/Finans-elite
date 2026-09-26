// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { AuditFlag, AuditFlagRegistry } from "../api/audit";
import { AuditFlags } from "./AuditFlags";

/**
 * Реестр флагов. Проверяется главное решение методики: денежная мера есть не у
 * всякого флага, и экран нигде не делает вид, что есть.
 */

afterEach(cleanup);

function flag(over: Partial<AuditFlag> = {}): AuditFlag {
  return {
    code: "receivables_outpace_revenue", severity: "risk",
    title: "Дебиторка растёт быстрее выручки",
    detail: "В периоде 2024 дебиторка выросла на 60% против 10% у выручки.",
    periods: [1], impact: "100",
    evidence: { expected_receivables: "220", revenue_growth: "0.1" },
    ...over,
  };
}

const PERIODS = ["2023", "2024"];

function show(registry: Partial<AuditFlagRegistry>) {
  render(<AuditFlags periods={PERIODS}
                     registry={{ flags: [], priced_total: "0", unpriced: 0, ...registry }} />);
}

describe("Реестр флагов", () => {
  it("пустой реестр объясняет, чего он не проверял", () => {
    // Иначе «флагов нет» читается как «проверено всё» — а проверена только
    // агрегатная отчётность, без выписок и договоров.
    show({});
    expect(screen.getByText("Красных флагов нет")).toBeTruthy();
    expect(screen.getByText(/выписки, договоры и/)).toBeTruthy();
  });

  it("флаг назван, объяснён и привязан к периоду", () => {
    show({ flags: [flag()], priced_total: "100" });
    expect(screen.getByText("Дебиторка растёт быстрее выручки")).toBeTruthy();
    expect(screen.getByText("2024")).toBeTruthy();
    expect(screen.getByText("Риск")).toBeTruthy();
  });

  it("флаг без денежной меры говорит об этом словами, а не нулём", () => {
    // Ноль означал бы «влияние посчитано и равно нулю»; меры не существует вовсе.
    show({ flags: [flag({ code: "negative_equity", impact: null })], unpriced: 1 });
    expect(screen.getByText("мера не определена")).toBeTruthy();
    // и итог не показывает «0 ₽»: это читалось бы как «риски ничего не стоят»
    expect(screen.queryByText("0 ₽")).toBeNull();
    expect(screen.getByText("не определено")).toBeTruthy();
    expect(screen.getByText(/Ни один из найденных флагов не выражается суммой/)).toBeTruthy();
  });

  it("итог не выдаёт сумму оценённых за полную цену рисков", () => {
    // Самое опасное упрощение всего экрана: сложить что считается и подписать «итого».
    show({
      flags: [flag(), flag({ code: "negative_equity", impact: null })],
      priced_total: "100", unpriced: 1,
    });
    const note = screen.getByText(/только по флагам с денежной мерой/);
    expect(note.textContent).toContain("1");
    expect(note.textContent).toContain("предмет переговоров");
  });

  it("когда мера есть у всех, оговорки нет", () => {
    show({ flags: [flag()], priced_total: "100", unpriced: 0 });
    expect(screen.getByText(/Все флаги имеют денежную меру/)).toBeTruthy();
    expect(screen.queryByText(/предмет переговоров/)).toBeNull();
  });

  it("обоснование раскрывается по клику и подписано словами", () => {
    show({ flags: [flag()], priced_total: "100" });
    expect(screen.queryByText("Дебиторка при прежней оборачиваемости")).toBeNull();
    fireEvent.click(screen.getByText("Дебиторка растёт быстрее выручки"));
    // код слагаемого читателю ничего не говорит — нужна подпись
    expect(screen.getByText("Дебиторка при прежней оборачиваемости")).toBeTruthy();
    expect(screen.queryByText("expected_receivables")).toBeNull();
  });

  it("счётчик называет число тяжёлых флагов отдельно", () => {
    show({
      flags: [flag(), flag({ code: "inventory_outpace_cogs", severity: "warning" })],
      priced_total: "100",
    });
    expect(screen.getByText(/2 флагов · из них 1 тяжёлых/)).toBeTruthy();
  });
});
