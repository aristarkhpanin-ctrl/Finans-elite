import { describe, expect, it } from "vitest";
import type { Resource, Stage } from "../../api/model";
import { computeBudget, resolveSchedule, stageCost } from "./calendar.logic";

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
