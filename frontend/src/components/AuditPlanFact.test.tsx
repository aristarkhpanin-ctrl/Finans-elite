// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AuditPlanFact as Result,
  AuditPlanFactRow,
  AuditRealizedFlag,
  RealizedFlag,
} from "../api/audit";
import { AuditPlanFact } from "./AuditPlanFact";

/**
 * План-факт. Проверяются решения методики, которые легко потерять при следующей правке
 * экрана: оценка учитывает направление, нулевой факт назван двусмысленным, предсказанное
 * и фактическое подписаны по источнику, а «не оценено» не превращается в ноль.
 */

afterEach(cleanup);

function row(over: Partial<AuditPlanFactRow> = {}): AuditPlanFactRow {
  return { code: "I_REVENUE", label: "Выручка", direction: "higher", plan: "4000",
           fact: "3700", delta: "-300", delta_share: "-0.075", verdict: "on_plan",
           note: "", ...over };
}

function flag(over: Partial<AuditRealizedFlag> = {}): AuditRealizedFlag {
  return { code: "receivables_outpace_revenue", title: "Дебиторка растёт быстрее выручки",
           severity: "risk", predicted: "209", realized: false, actual_cost: null,
           note: "", ...over };
}

function result(over: Partial<Result> = {}): Result {
  return {
    available: true, periods: ["2023", "2024"], rows: [row()], flags: [flag()],
    predicted_total: "0", realized_total: "0", unpriced_realized: 0, orphan_marks: [],
    caveats: [],
    not_computed: ["Доходность вложения — нужна цена, по которой сделка закрылась."],
    ...over,
  };
}

function show(over: Partial<Result> = {}, opts: {
  plan?: Record<string, string[]>; marks?: RealizedFlag[];
  onPlan?: (n: Record<string, string[]>) => void;
  onMarks?: (n: RealizedFlag[]) => void;
} = {}) {
  render(<AuditPlanFact result={result(over)} periods={["2023", "2024"]}
                        plan={opts.plan ?? {}} marks={opts.marks ?? []}
                        onPlan={opts.onPlan ?? (() => {})}
                        onMarks={opts.onMarks ?? (() => {})} />);
}

describe("План-факт", () => {
  it("без плана сравнения нет, но ввод плана предложен", () => {
    // «Плана нет» — это не «всё сошлось».
    show({ available: false, rows: [],
           caveats: ["Прогноз продавца не введён — сравнивать факт не с чем."] });
    expect(screen.getByText(/Прогноз продавца не введён/)).toBeTruthy();
    expect(screen.queryByText("Развёрнутый план-факт")).toBeNull();
    expect(screen.getByText("Прогноз продавца")).toBeTruthy();
  });

  it("охват сравнения назван, а не подразумевается", () => {
    show();
    expect(screen.getByText(/сравниваются периоды: 2023, 2024/)).toBeTruthy();
  });

  it("оценка учитывает направление: расход ниже плана — успех", () => {
    // Иначе «−12%» у себестоимости красится как недобор.
    show({ rows: [row({ code: "I_COGS", label: "Себестоимость", direction: "lower",
                        delta: "-114", delta_share: "-0.2", verdict: "better" })] });
    const line = document.querySelector(".pf-table tbody tr")!;
    expect(line.className).toContain("pf--better");
    expect(line.textContent).toContain("лучше плана");
  });

  it("недобор выручки красится как провал", () => {
    show({ rows: [row({ verdict: "worse", delta_share: "-0.25" })] });
    expect(document.querySelector(".pf-table tbody tr")!.className)
      .toContain("pf--worse");
  });

  it("отклонение в пределах порога показано числом, но не оценено", () => {
    show();
    const line = document.querySelector(".pf-table tbody tr")!;
    expect(line.className).toContain("pf--on-plan");
    expect(line.textContent).toContain("в пределах порога");
    expect(line.textContent).toContain("-7,5%");
  });

  it("нулевой факт назван двусмысленным прямо в строке", () => {
    show({ rows: [row({ fact: "0", delta: "-4000", delta_share: "-1", verdict: "worse",
                        note: "факт нулевой: это либо полный недобор, либо период ещё "
                              + "не отражён в отчётности — платформа их не различает" })] });
    expect(screen.getByText(/платформа их не различает/)).toBeTruthy();
  });

  it("предсказанное и фактическое подписаны по источнику", () => {
    // Иначе «дисконт окупился» читается как один расчёт, а это сравнение
    // посчитанного с введённым.
    show({ predicted_total: "209", realized_total: "150" });
    expect(screen.getByText(/сумма влияния флагов, отмеченных как сработавшие/))
      .toBeTruthy();
    expect(screen.getByText(/введено аналитиком — платформа причин не видит/))
      .toBeTruthy();
  });

  it("флаг без денежной меры не сопоставляется, и сказано почему", () => {
    show({ flags: [flag({ code: "negative_equity", title: "Отрицательный капитал",
                          predicted: null })] });
    expect(screen.getByText(/денежной меры нет — не сопоставляется/)).toBeTruthy();
    expect(screen.getByText(/предсказанной величины у них нет вовсе/)).toBeTruthy();
  });

  it("отметка «сработал» уходит наверх, а не теряется", () => {
    const onMarks = vi.fn();
    show({}, { onMarks });
    fireEvent.click(screen.getByLabelText("Дебиторка растёт быстрее выручки: сработал"));
    expect(onMarks).toHaveBeenCalledWith([
      { code: "receivables_outpace_revenue", realized: true, actual_cost: null, note: "" },
    ]);
  });

  it("пустая фактическая потеря уходит как null, а не как ноль", () => {
    // «Факт ещё не оценён» и «обошёлся в ноль» — разные вещи.
    const onMarks = vi.fn();
    show({}, { marks: [{ code: "receivables_outpace_revenue", realized: true,
                         actual_cost: "150", note: "" }], onMarks });
    fireEvent.change(
      screen.getByLabelText("Дебиторка растёт быстрее выручки: фактическая потеря"),
      { target: { value: "" } });
    expect(onMarks.mock.calls[0][0][0].actual_cost).toBeNull();
  });

  it("план вводится по тем же периодам, что и отчётность", () => {
    const onPlan = vi.fn();
    show({}, { onPlan });
    fireEvent.change(screen.getByLabelText("Выручка, 2024: план"),
                     { target: { value: "2200" } });
    expect(onPlan).toHaveBeenCalledWith({ I_REVENUE: ["", "2200"] });
  });

  it("сказано, что факт вводить не нужно", () => {
    // Второго источника фактических чисел план-факт не заводит.
    show();
    expect(screen.getByText(/Факт вводить не нужно/)).toBeTruthy();
  });

  it("оговорки выводятся, а не проглатываются", () => {
    show({ caveats: ["Отметки по флагам, которых в текущем реестре больше нет (x)."] });
    expect(screen.getByText(/которых в текущем реестре больше нет/)).toBeTruthy();
  });

  it("сказано, чего план-факт не считает", () => {
    show();
    expect(screen.getByText("Чего план-факт не считает")).toBeTruthy();
    expect(screen.getByText(/Доходность вложения/)).toBeTruthy();
  });

  it("без периодов вносить план не к чему, и это сказано", () => {
    render(<AuditPlanFact result={result({ available: false, rows: [] })} periods={[]}
                          plan={{}} marks={[]} onPlan={() => {}} onMarks={() => {}} />);
    expect(screen.getByText(/Периоды не заданы — вносить план не к чему/)).toBeTruthy();
  });
});
