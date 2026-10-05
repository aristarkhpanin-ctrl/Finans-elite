// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Stage } from "../../api/model";
import { BudgetGantt, linkPath } from "./BudgetGantt";
import { computeBudget, resolveSchedule } from "./calendar.logic";

afterEach(cleanup);

const stages: Stage[] = [
  { id: "a", name: "Стройка", kind: "expense", start_month: 0, duration_months: 2, cost: "200" },
  { id: "b", name: "Монтаж", kind: "asset", predecessor_id: "a", start_month: 0,
    duration_months: 1, cost: "900", asset_life_months: 12 },
];

function draw(props: Partial<React.ComponentProps<typeof BudgetGantt>> = {}) {
  const st = props.stages ?? stages;
  return render(
    <BudgetGantt n={6} stages={st} resources={[]}
                 budget={computeBudget(st, [], 6)} sched={resolveSchedule(st)} {...props} />,
  );
}

describe("linkPath", () => {
  it("вперёд — прямой путь в три сегмента", () => {
    // преемник начинается правее финиша предшественника: вправо, вниз, вправо
    expect(linkPath(100, 15, 200, 45)).toBe("M100,15 H109 V45 H197");
  });

  it("вплотную или назад — обход между строками (не ложится на полосы)", () => {
    const d = linkPath(100, 15, 100, 45);      // нулевой лаг: старт = финиш предшественника
    expect(d).toBe("M100,15 H109 V30 H91 V45 H97");
    expect(d.split("V").length).toBe(3);        // два поворота по вертикали — это обход
  });
});

describe("BudgetGantt", () => {
  it("рисует стрелку связи «финиш → старт»", () => {
    const { container } = draw();
    expect(container.querySelectorAll(".bg-gantt__link").length).toBe(1);
  });

  it("без связей стрелок нет", () => {
    const { container } = draw({ stages: [stages[0]] });
    expect(container.querySelector(".bg-gantt__links")).toBeNull();
  });

  it("без обработчика правки полосы не тянутся (режим только для чтения)", () => {
    const { container } = draw();
    expect(container.querySelectorAll(".bg-gantt__bar--drag").length).toBe(0);
    expect(container.querySelectorAll(".bg-gantt__handle").length).toBe(0);
  });

  it("с обработчиком у каждого листа появляются полоса-ручка и два края", () => {
    const { container } = draw({ onStageChange: vi.fn() });
    expect(container.querySelectorAll(".bg-gantt__bar--drag").length).toBe(2);
    expect(container.querySelectorAll(".bg-gantt__handle").length).toBe(4);
  });

  it("группу тянуть нельзя: её сроки — свёртка потомков", () => {
    const withGroup: Stage[] = [
      { id: "g", name: "Подготовка", start_month: 0, duration_months: 1 },
      { id: "c", name: "Работы", parent_id: "g", kind: "expense",
        start_month: 0, duration_months: 2, cost: "100" },
    ];
    const { container } = draw({ stages: withGroup, onStageChange: vi.fn() });
    // тянутся только листья — полос две, перетаскиваемая одна
    expect(container.querySelectorAll(".bg-gantt__bar").length).toBe(2);
    expect(container.querySelectorAll(".bg-gantt__bar--drag").length).toBe(1);
  });

  it("масштаб и денежные строки на месте", () => {
    draw();
    expect(screen.getByText("Квартал")).toBeTruthy();
    expect(screen.getByText("Освоение")).toBeTruthy();
    expect(screen.getByText("Не оплачено")).toBeTruthy();
  });
});
