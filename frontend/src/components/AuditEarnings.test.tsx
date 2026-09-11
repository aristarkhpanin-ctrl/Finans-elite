// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuditEarnings as Quality, EarningsAdjustment } from "../api/audit";
import { AuditEarnings } from "./AuditEarnings";

/**
 * Качество прибыли. Проверяются два решения методики, которые легко потерять при
 * следующей правке: показатель назван своим именем (EBIT ≠ EBITDA) и буква качества
 * подана как соглашение с показанным расхождением, а не как измеренная истина.
 */

afterEach(cleanup);

const PERIODS = ["2023", "2024"];

function quality(over: Partial<Quality> = {}): Quality {
  return {
    base_code: "EBIT", reported: ["200", "240"], normalized: ["200", "240"],
    adjustments: [], grade: "A", grade_note: "Отчётная прибыль подтверждается.",
    deviation: "0", ...over,
  };
}

function show(over: Partial<Quality> = {}, opts: {
  adjustments?: EarningsAdjustment[]; hasDepreciation?: boolean; onChange?: () => void;
} = {}) {
  render(<AuditEarnings quality={quality(over)} periods={PERIODS}
                        adjustments={opts.adjustments ?? []}
                        hasDepreciation={opts.hasDepreciation ?? false}
                        onChange={opts.onChange ?? (() => {})} />);
}

describe("Качество прибыли", () => {
  it("без амортизации показатель назван EBIT и объяснено почему", () => {
    // Подписать EBIT словом EBITDA — значит сдвинуть мультипликатор сделки на всю
    // амортизацию. Поэтому имя показателя видно, и видно, чего не хватает.
    show();
    expect(screen.getByText("EBIT")).toBeTruthy();
    expect(screen.getByText(/Амортизация не введена/)).toBeTruthy();
    expect(screen.getByText(/EBIT по отчётности/)).toBeTruthy();
  });

  it("с амортизацией показатель называется EBITDA и подсказки нет", () => {
    show({ base_code: "EBITDA" }, { hasDepreciation: true });
    expect(screen.getByText("EBITDA")).toBeTruthy();
    expect(screen.queryByText(/Амортизация не введена/)).toBeNull();
    expect(screen.getByText(/EBITDA нормализованный/)).toBeTruthy();
  });

  it("буква качества подана как соглашение и показывает расхождение", () => {
    // Иначе A/B/C читается как измеренная истина, а это договорённость о шкале.
    show({ grade: "B", deviation: "0.125", grade_note: "Прибыль требует оговорок." });
    expect(screen.getByText("B")).toBeTruthy();
    const note = screen.getByText(/Расхождение с отчётным/);
    expect(note.textContent).toContain("12,5%");
    expect(note.textContent).toContain("соглашение методики, а не измерение");
  });

  it("без буквы блок оценки не рисуется", () => {
    // Нулевой отчётный показатель сравнивать не с чем — «A» здесь было бы враньём.
    show({ grade: null, deviation: null });
    expect(screen.queryByText(/Расхождение с отчётным/)).toBeNull();
  });

  it("применённые корректировки видны в таблице с видом", () => {
    show({
      normalized: ["200", "160"],
      adjustments: [{ label: "Продажа склада", kind: "one_off",
                      kind_label: "Разовый доход или расход",
                      amounts: ["0", "-80"], total: "-80" }],
    });
    expect(screen.getByText("Продажа склада")).toBeTruthy();
    expect(screen.getByText("Разовый доход или расход")).toBeTruthy();
  });

  it("пустой список корректировок — содержательный ответ, а не пустота", () => {
    show();
    expect(screen.getByText(/отчётность принята как есть/)).toBeTruthy();
  });

  it("корректировка без причины предупреждает, что не применится", () => {
    // Иначе это выяснится по неизменившемуся итогу, и человек решит, что сломалось.
    show({}, { adjustments: [{ label: "", kind: "one_off", amounts: [] }] });
    expect(screen.getByText(/Без причины корректировка не применяется/)).toBeTruthy();
  });

  it("заполненная причина снимает предупреждение", () => {
    show({}, { adjustments: [{ label: "Разовое", kind: "one_off", amounts: [] }] });
    expect(screen.queryByText(/Без причины корректировка не применяется/)).toBeNull();
  });

  it("правка суммы уходит наверх со знаком, а не теряется", () => {
    const onChange = vi.fn();
    show({}, { adjustments: [{ label: "Разовое", kind: "one_off", amounts: [] }], onChange });
    fireEvent.change(screen.getByLabelText("2024: сумма корректировки"),
                     { target: { value: "-80" } });
    expect(onChange).toHaveBeenCalledWith([
      { label: "Разовое", kind: "one_off", amounts: ["", "-80"] },
    ]);
  });

  it("добавление корректировки создаёт пустую строку с причиной под заполнение", () => {
    const onChange = vi.fn();
    show({}, { onChange });
    fireEvent.click(screen.getByText(/Корректировка/));
    expect(onChange).toHaveBeenCalledWith([{ label: "", kind: "one_off", amounts: [] }]);
  });
});
