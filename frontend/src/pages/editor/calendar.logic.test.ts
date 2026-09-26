import { describe, expect, it } from "vitest";
import type { Resource, Stage } from "../../api/model";
import { applyDrag, computeBudget, resolveSchedule, stageCost } from "./calendar.logic";

describe("resolveSchedule", () => {
  it("предшественник сдвигает старт (финиш→старт + лаг)", () => {
    const a: Stage = { id: "a", start_month: 0, duration_months: 2 };
    const b: Stage = { id: "b", predecessor_id: "a", start_month: 1, duration_months: 1 };
    const s = resolveSchedule([a, b]);
    expect(s.get("a")).toEqual({ start: 0, finish: 2 });
    expect(s.get("b")).toEqual({ start: 3, finish: 4 }); // 2 (финиш a) + 1 (лаг)
  });

  it("цикл не зацикливается", () => {
    const a: Stage = { id: "a", predecessor_id: "b", start_month: 0, duration_months: 1 };
    const b: Stage = { id: "b", predecessor_id: "a", start_month: 1, duration_months: 1 };
    expect(() => resolveSchedule([a, b])).not.toThrow();
  });
});

describe("stageCost", () => {
  it("Σ количество×цена ресурса", () => {
    const res: Resource[] = [{ id: "r1", unit_price: "100" }];
    const byRes = new Map(res.map((r) => [r.id, r]));
    const st: Stage = { id: "s1", resources: [{ resource_id: "r1", quantity: "6" }] };
    expect(stageCost(st, byRes)).toBe(600);
  });

  it("прямая стоимость без ресурсов", () => {
    expect(stageCost({ id: "s", cost: "250" }, new Map())).toBe(250);
  });
});

describe("computeBudget", () => {
  it("свёртка групп: стоимость и график", () => {
    const grp: Stage = { id: "g", kind: "expense", start_month: 0, duration_months: 1 };
    const a: Stage = { id: "a", kind: "expense", parent_id: "g", start_month: 0, duration_months: 2, cost: "200" };
    const b: Stage = { id: "b", kind: "asset", parent_id: "g", start_month: 2, duration_months: 1, cost: "900" };
    const bud = computeBudget([grp, a, b], [], 5);
    expect(bud.total).toBe(1100);
    expect(bud.monthly).toEqual([100, 100, 0, 900, 0]); // a 100/мес, актив b 900 в мес. 3
    const g = bud.rows.find((r) => r.id === "g")!;
    expect(g.cost).toBe(1100);
    expect(g.start).toBe(0);
    expect(g.finish).toBe(3);
  });
});

/**
 * Финансовый разрез сметы (бюджетный Гантт). Числа повторяют бэкенд-тесты
 * `test_budget_finance.py`: если зеркало разойдётся с движком, живой предпросмотр
 * покажет одно, а расчёт даст другое.
 */
describe("computeBudget — освоение и оплата", () => {
  const resources: Resource[] = [
    { id: "r", name: "Подрядчик", unit_price: "300", payment_delay_months: 2 },
  ];
  const stages: Stage[] = [{
    id: "s", kind: "expense", start_month: 0, duration_months: 2,
    resources: [{ resource_id: "r", quantity: "2" }],
  }];

  it("оплата сдвинута на отсрочку ресурса", () => {
    const b = computeBudget(stages, resources, 6);
    expect(b.monthly).toEqual([300, 300, 0, 0, 0, 0]);
    expect(b.monthlyCash).toEqual([0, 0, 300, 300, 0, 0]);
    expect(b.total).toBe(600);
  });

  it("кредиторка = начислено − оплачено (та же величина, что B23)", () => {
    expect(computeBudget(stages, resources, 6).payables).toEqual([300, 600, 300, 0, 0, 0]);
  });

  it("прямая стоимость платится в момент освоения", () => {
    const b = computeBudget(
      [{ id: "s", kind: "expense", start_month: 1, duration_months: 2, cost: "400" }], [], 4);
    expect(b.monthly).toEqual([0, 200, 200, 0]);
    expect(b.monthlyCash).toEqual(b.monthly);
    expect(b.payables).toEqual([0, 0, 0, 0]);
  });

  it("этап-актив: разово в месяц финиша, оплата = освоению (отсрочка не применяется)", () => {
    const b = computeBudget([{
      id: "a", kind: "asset", start_month: 0, duration_months: 3, asset_life_months: 12,
      resources: [{ resource_id: "r", quantity: "3" }],
    }], resources, 6);
    expect(b.monthly).toEqual([0, 0, 0, 900, 0, 0]);
    expect(b.monthlyCash).toEqual(b.monthly);
  });

  it("стоимость в конце (on_finish) начисляется одним месяцем", () => {
    const b = computeBudget([{
      id: "s", kind: "expense", start_month: 0, duration_months: 3, cost: "600",
      cost_timing: "on_finish",
    }], [], 4);
    expect(b.monthly).toEqual([0, 0, 600, 0]);
  });

  it("S-кривые: накопленное освоение и оплата", () => {
    const b = computeBudget(
      [{ id: "s", kind: "expense", start_month: 0, duration_months: 2, cost: "200" }], [], 4);
    expect(b.cumulative).toEqual([100, 200, 200, 200]);
    expect(b.cumulativeCash).toEqual(b.cumulative);
  });
});

describe("computeBudget — трактовка стоимости", () => {
  const stages: Stage[] = [
    { id: "e", kind: "expense", start_month: 0, duration_months: 1, cost: "100" },
    { id: "d", kind: "expense", start_month: 0, duration_months: 1, cost: "200", amortize_months: 6 },
    { id: "a", kind: "asset", start_month: 0, duration_months: 1, cost: "300", asset_life_months: 12 },
    { id: "p", kind: "production", start_month: 0, duration_months: 1 },
  ];

  it("разбивка по трактовке в сумме даёт смету", () => {
    const b = computeBudget(stages, [], 12);
    expect(b.expenseTotal).toBe(100);     // издержка периода (I21)
    expect(b.deferredTotal).toBe(200);    // расходы будущих периодов (B15)
    expect(b.assetTotal).toBe(300);       // капвложение (C14 → B14)
    expect(b.expenseTotal + b.deferredTotal + b.assetTotal).toBe(b.total);
  });

  it("этап производства стоимости не несёт", () => {
    const p = computeBudget(stages, [], 12).rows.find((r) => r.id === "p")!;
    expect(p.treatment).toBe("none");
    expect(p.cost).toBe(0);
  });

  it("смешанной группе трактовка потомка не приписывается", () => {
    const b = computeBudget([
      { id: "g", start_month: 0, duration_months: 1 },
      { id: "c1", parent_id: "g", kind: "expense", start_month: 0, duration_months: 1, cost: "100" },
      { id: "c2", parent_id: "g", kind: "asset", start_month: 0, duration_months: 1, cost: "300", asset_life_months: 12 },
    ], [], 4);
    expect(b.rows.find((r) => r.id === "g")!.treatment).toBe("mixed");
  });

  it("однородная группа наследует трактовку потомков", () => {
    const b = computeBudget([
      { id: "g", start_month: 0, duration_months: 1 },
      { id: "c1", parent_id: "g", kind: "expense", start_month: 0, duration_months: 1, cost: "100" },
      { id: "c2", parent_id: "g", kind: "expense", start_month: 1, duration_months: 1, cost: "50" },
    ], [], 4);
    const g = b.rows.find((r) => r.id === "g")!;
    expect(g.treatment).toBe("expense");
    expect(g.monthly).toEqual([100, 50, 0, 0]);   // ряды группы — сумма рядов потомков
  });
});

describe("computeBudget — пустой план инертен", () => {
  it("без этапов смета пуста, ряды нулевые", () => {
    const b = computeBudget([], [], 6);
    expect(b.rows).toEqual([]);
    expect(b.total).toBe(0);
    expect(b.monthlyCash).toEqual([0, 0, 0, 0, 0, 0]);
    expect(b.expenseTotal + b.deferredTotal + b.assetTotal).toBe(0);
  });
});

describe("applyDrag — правка сроков перетаскиванием", () => {
  const st: Stage = { id: "s", kind: "expense", start_month: 4, duration_months: 3 };

  it("тело полосы двигает старт, длительность не трогает", () => {
    expect(applyDrag(st, "move", 2)).toEqual({ start_month: 6, duration_months: 3 });
    expect(applyDrag(st, "move", -3)).toEqual({ start_month: 1, duration_months: 3 });
  });

  it("влево старт упирается в ноль: отрицательного месяца (и лага) в модели нет", () => {
    expect(applyDrag(st, "move", -99)).toEqual({ start_month: 0, duration_months: 3 });
  });

  it("правый край меняет длительность, не короче месяца", () => {
    expect(applyDrag(st, "end", 2)).toEqual({ start_month: 4, duration_months: 5 });
    expect(applyDrag(st, "end", -99)).toEqual({ start_month: 4, duration_months: 1 });
  });

  it("левый край двигает старт, оставляя финиш на месте", () => {
    const r = applyDrag(st, "start", -2);
    expect(r).toEqual({ start_month: 2, duration_months: 5 });
    expect(r.start_month + r.duration_months).toBe(7);   // финиш прежний: 4 + 3
  });

  it("левый край не схлопывает этап в ноль", () => {
    const r = applyDrag(st, "start", 99);
    expect(r).toEqual({ start_month: 6, duration_months: 1 });
    expect(r.start_month + r.duration_months).toBe(7);   // финиш всё ещё прежний
  });

  it("левый край не уводит старт в минус", () => {
    expect(applyDrag({ id: "z", start_month: 1, duration_months: 4 }, "start", -5))
      .toEqual({ start_month: 0, duration_months: 5 });
  });

  it("нулевой сдвиг ничего не меняет", () => {
    expect(applyDrag(st, "move", 0)).toEqual({ start_month: 4, duration_months: 3 });
  });

  it("перетаскивание двигает деньги, а не только сроки", () => {
    const paid: Stage = { ...st, cost: "600" };
    const moved: Stage = { ...paid, ...applyDrag(paid, "move", 2) };
    const before = computeBudget([paid], [], 12);
    const after = computeBudget([moved], [], 12);
    expect(before.monthly.slice(4, 7)).toEqual([200, 200, 200]);
    expect(after.monthly.slice(6, 9)).toEqual([200, 200, 200]);
    expect(after.total).toBe(before.total);              // смета та же, сдвинут график
  });
});
