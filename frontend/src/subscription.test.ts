import { describe, expect, it } from "vitest";
import { subscriptionPreview } from "./subscription";

/**
 * Предпросмотр абонентской базы (SPEC §5).
 *
 * Числа здесь — **те же**, что в `backend/tests/test_subscription.py`: зеркало без
 * фикстуры-эталона держится на том, что обе стороны проверены одним и тем же примером,
 * посчитанным на бумаге. Рекуррента одна, и расходиться ей негде; если она всё же
 * изменится, разойдутся и оба набора тестов, а не один экран молча.
 */

const sub = (starting_base: string, newPerMonth: number[], churn: string) => ({
  starting_base,
  new_per_month: newPerMonth.map(String),
  churn_monthly: churn,
});

describe("subscriptionPreview", () => {
  it("притоком растит, оттоком уменьшает — 100 на старте, 10 приходят, 10% уходят", () => {
    const { base } = subscriptionPreview(sub("100", Array(6).fill(10), "0.1"), 6);
    expect(base).toEqual([100, 100, 100, 100, 100, 100]);
  });

  it("отток берётся до притока: пришедший в этом месяце в нём же не уходит", () => {
    const { base, churned } = subscriptionPreview(sub("50", [100], "0.2"), 1);
    expect(base).toEqual([140]);      // 50 − 10 + 100, а не (50 + 100) · 0,8 = 120
    expect(churned).toEqual([10]);
  });

  it("база идёт к потолку «приток ÷ отток», а не растёт вечно", () => {
    const { base, ceiling } = subscriptionPreview(sub("0", Array(120).fill(60), "0.05"), 120);
    expect(ceiling).toBe(1200);
    expect(base[119]).toBeLessThan(1200);
    expect(base[119]).toBeGreaterThan(1188);
  });

  it("нулевой отток — просто накопление, и потолка нет", () => {
    const { base, ceiling } = subscriptionPreview(sub("10", Array(4).fill(5), "0"), 4);
    expect(base).toEqual([15, 20, 25, 30]);
    expect(ceiling).toBeNull();
  });

  it("отток 100% оставляет ровно пришедших в этом месяце", () => {
    const { base } = subscriptionPreview(sub("500", Array(3).fill(7), "1"), 3);
    expect(base).toEqual([7, 7, 7]);
  });

  it("короткий ряд притока — дальше никто не приходит, а не «повторить последнее»", () => {
    const { base } = subscriptionPreview(sub("0", [100], "0.5"), 3);
    expect(base).toEqual([100, 50, 25]);
  });

  it("непостоянный приток потолка не даёт — одного числа не существует", () => {
    expect(subscriptionPreview(sub("0", [10, 20, 30], "0.1"), 3).ceiling).toBeNull();
  });

  it("старт продукта гейтит приток, а не выведенную базу", () => {
    const { base } = subscriptionPreview(sub("1000", Array(6).fill(50), "0.1"), 6, 3);
    expect(base.slice(0, 3)).toEqual([0, 0, 0]);
    expect(base[3]).toBe(50);                       // ровно первый приток
    expect(base[4]).toBeCloseTo(50 * 0.9 + 50, 10); // а не 1000, накопленная до старта
  });

  it("пустой и испорченный ввод не рушат предпросмотр", () => {
    const { base } = subscriptionPreview(
      { starting_base: "", new_per_month: ["", "не число", "5"], churn_monthly: "" }, 3);
    expect(base).toEqual([0, 0, 5]);
  });

  it("запятая-десятичная читается: в русском продукте её пишут именно так", () => {
    const { base } = subscriptionPreview(sub("100", [0], "0,25"), 1);
    expect(base).toEqual([75]);
  });
});
