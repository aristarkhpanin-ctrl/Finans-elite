import { describe, expect, it } from "vitest";
import type { Resource, Stage } from "../../api/model";
import fixture from "../../fixtures/calendarBudget.json";
import { computeBudget, resolveSchedule } from "./calendar.logic";

/**
 * Сверка зеркала с движком.
 *
 * `calendar.logic.ts` повторяет правила `calc_core/engine/calendar.py`, чтобы Гантт
 * показывал деньги, пока правки не отправлены на сервер. Раньше числа в тестах обеих
 * сторон были выписаны руками по отдельности — правка движка роняла питоновские тесты, а
 * зеркало молча считало по-старому, и предпросмотр расходился с расчётом.
 *
 * Здесь тот же вход прогоняется через зеркало и сверяется с выходом движка. Фикстуру
 * генерирует `backend/scripts/dump_calendar_fixture.py`, её свежесть стережёт
 * `test_calendar_fixture.py`. Если этот тест упал — зеркало отстало от движка.
 */

const { n, stages, resources, budget } = fixture as unknown as {
  n: number;
  stages: Stage[];
  resources: Resource[];
  budget: {
    total: string; expenseTotal: string; deferredTotal: string; assetTotal: string;
    monthly: string[]; monthlyCash: string[];
    cumulative: string[]; cumulativeCash: string[]; payables: string[];
    rows: { id: string; start: number; finish: number; cost: string; treatment: string;
            monthly: string[]; monthlyCash: string[] }[];
  };
};

/** Деньги → целые копейки: сравниваем точно, без хвостов двоичной плавающей точки. */
const kop = (v: number | string): number => Math.round(Number(v) * 100);
const kops = (xs: (number | string)[]): number[] => xs.map(kop);

const mirror = computeBudget(stages, resources, n);
const byId = new Map(mirror.rows.map((r) => [r.id, r]));

describe("Зеркало сметы совпадает с движком", () => {
  it("итог и разбивка по трактовке", () => {
    expect(kop(mirror.total)).toBe(kop(budget.total));
    expect(kop(mirror.expenseTotal)).toBe(kop(budget.expenseTotal));
    expect(kop(mirror.deferredTotal)).toBe(kop(budget.deferredTotal));
    expect(kop(mirror.assetTotal)).toBe(kop(budget.assetTotal));
  });

  it("помесячное освоение и оплата", () => {
    expect(kops(mirror.monthly)).toEqual(kops(budget.monthly));
    expect(kops(mirror.monthlyCash)).toEqual(kops(budget.monthlyCash));
  });

  it("накопленные ряды и неоплаченные обязательства", () => {
    expect(kops(mirror.cumulative)).toEqual(kops(budget.cumulative));
    expect(kops(mirror.cumulativeCash)).toEqual(kops(budget.cumulativeCash));
    expect(kops(mirror.payables)).toEqual(kops(budget.payables));
  });

  it("состав строк — те же этапы в том же порядке", () => {
    expect(mirror.rows.map((r) => r.id)).toEqual(budget.rows.map((r) => r.id));
  });

  it.each(fixture.budget.rows.map((r) => r.id))("строка «%s»: сроки, стоимость, трактовка", (id) => {
    const got = byId.get(id)!;
    const want = budget.rows.find((r) => r.id === id)!;
    expect({ start: got.start, finish: got.finish }).toEqual({ start: want.start, finish: want.finish });
    expect(kop(got.cost)).toBe(kop(want.cost));
    expect(got.treatment).toBe(want.treatment);
    expect(kops(got.monthly)).toEqual(kops(want.monthly));
    expect(kops(got.monthlyCash)).toEqual(kops(want.monthlyCash));
  });

  it("расписание разрешает связи так же, как движок", () => {
    // Сверяются только листья: у группы собственных сроков нет — и движок, и зеркало
    // берут их свёрткой потомков, а не из разрешения связей.
    const groups = new Set(stages.map((s) => s.parent_id).filter(Boolean));
    const sched = resolveSchedule(stages);
    const leaves = budget.rows.filter((r) => !groups.has(r.id));
    expect(leaves.length).toBeGreaterThan(0);
    for (const want of leaves) {
      const got = sched.get(want.id)!;
      expect({ id: want.id, start: got.start, finish: got.finish })
        .toEqual({ id: want.id, start: want.start, finish: want.finish });
    }
  });
});
