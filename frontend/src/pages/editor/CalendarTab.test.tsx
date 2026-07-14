// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { InvestmentPlan } from "../../api/model";
import { CalendarTab } from "./CalendarTab";

afterEach(cleanup);

function iv(stages: InvestmentPlan["calendar"]): InvestmentPlan {
  return { assets: [], calendar: stages };
}

describe("CalendarTab", () => {
  it("пустой план — приглашение добавить этап", () => {
    render(<CalendarTab n={6} investment={iv({ stages: [], resources: [] })} products={[]} onChange={() => {}} />);
    expect(screen.getByText("Нет этапов")).toBeTruthy();
  });

  it("рендерит смету, Гантт и карточки этапов", () => {
    const investment = iv({
      stages: [
        { id: "a", name: "Стройка", kind: "expense", start_month: 0, duration_months: 2, cost: "200" },
        { id: "b", name: "Монтаж", kind: "asset", predecessor_id: "a", start_month: 0, duration_months: 1, cost: "900", asset_life_months: 12 },
      ],
      resources: [],
    });
    render(<CalendarTab n={6} investment={investment} products={[]} onChange={() => {}} />);
    expect(screen.getByText("Диаграмма Гантта")).toBeTruthy();
    expect(screen.getByText("Смета проекта")).toBeTruthy();
    expect(screen.getByText("График инвестиций (начисление по месяцам)")).toBeTruthy();
    // две карточки этапов (по числу name-инпутов)
    expect(screen.getAllByPlaceholderText("Название этапа").length).toBe(2);
  });
});
