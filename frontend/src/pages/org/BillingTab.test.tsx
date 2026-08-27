// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Plan, Subscription } from "../../api/org";
import { BillingTab } from "./BillingTab";

/**
 * Тарифы двух продуктов. Проверяется главное решение: «Элит» и «Аудит» продаются
 * порознь, поэтому экран показывает тариф выбранного продукта, а не общий, и подпись
 * квоты берётся из тарифа — у одного это проекты, у другого дела.
 */

const getPlans = vi.fn();
const getSubscription = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getPlans: (...a: unknown[]) => getPlans(...a),
  getSubscription: (...a: unknown[]) => getSubscription(...a),
}));
vi.mock("../../components/Toast", () => ({ useToast: () => vi.fn() }));

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

const BUSINESS_PLANS: Plan[] = [
  { code: "free", product: "business", name: "Бесплатный", price_rub: 0,
    price_on_request: false, max_units: 5, unit_name: "проектов", max_members: 5 },
  { code: "team", product: "business", name: "Команда", price_rub: 2900,
    price_on_request: false, max_units: 50, unit_name: "проектов", max_members: 25 },
] as Plan[];

const AUDIT_PLANS: Plan[] = [
  { code: "audit_trial", product: "audit", name: "Пробный", price_rub: 0,
    price_on_request: false, max_units: 5, unit_name: "дел", max_members: 5 },
  { code: "audit_team", product: "audit", name: "Команда", price_rub: 24000,
    price_on_request: false, max_units: 10, unit_name: "дел", max_members: 8 },
  { code: "audit_corp", product: "audit", name: "Корпоративный", price_rub: 0,
    price_on_request: true, max_units: null, unit_name: "дел", max_members: null },
] as Plan[];

function sub(product: string): Subscription {
  return product === "audit"
    ? { product, plan_code: "audit_trial", plan_name: "Пробный", status: "active",
        price_rub: 0, price_on_request: false, max_units: 5, unit_name: "дел",
        max_members: 5, used_units: 2, used_members: 1 } as Subscription
    : { product, plan_code: "free", plan_name: "Бесплатный", status: "active",
        price_rub: 0, price_on_request: false, max_units: 5, unit_name: "проектов",
        max_members: 5, used_units: 1, used_members: 1 } as Subscription;
}

async function show() {
  getPlans.mockImplementation((p: string) => Promise.resolve(
    p === "audit" ? AUDIT_PLANS : BUSINESS_PLANS));
  getSubscription.mockImplementation((_o: string, p: string) => Promise.resolve(sub(p)));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><BillingTab orgId="o1" canManage /></QueryClientProvider>);
  await screen.findByText("Тарифные планы");
}

/** Названия тарифов из карточек каталога (в блоке текущего тарифа имя повторяется). */
const cardNames = () =>
  [...document.querySelectorAll(".plan-card__name")].map((n) => n.textContent ?? "");

describe("Тарифы по продуктам", () => {
  it("по умолчанию показан «Элит» с его квотой проектов", async () => {
    await show();
    expect(screen.getByText("Проекты")).toBeTruthy();
    expect(screen.queryByText("Дела")).toBeNull();
    expect(screen.getByText(/5 проектов/)).toBeTruthy();
  });

  it("переключение продукта меняет и тариф, и единицу квоты", async () => {
    await show();
    fireEvent.click(screen.getByText("Финанс-Аудит"));
    await waitFor(() => expect(screen.getByText("Дела")).toBeTruthy());

    // запрошены именно тарифы аудита, а не общий каталог
    expect(getPlans).toHaveBeenCalledWith("audit");
    expect(getSubscription).toHaveBeenCalledWith("o1", "audit");
    expect(screen.getByText(/10 дел/)).toBeTruthy();
    expect(screen.queryByText("Проекты")).toBeNull();
  });

  it("«по запросу» показано словом, а не нулевой ценой", async () => {
    // Ноль вместо корпоративных условий читается как «бесплатно» — и тариф без
    // ограничений выглядел бы выгоднее платного.
    await show();
    fireEvent.click(screen.getByText("Финанс-Аудит"));
    await waitFor(() => expect(cardNames()).toContain("Корпоративный"));
    // цены читаются с карточек: тот же текст есть и в блоке текущего тарифа
    const prices = [...document.querySelectorAll(".plan-card__price")]
      .map((n) => n.textContent ?? "");
    expect(prices.filter((s) => s.includes("По запросу"))).toHaveLength(1);
    expect(prices.filter((s) => s.includes("Бесплатно"))).toHaveLength(1);
  });

  it("тарифы одного продукта не смешиваются с чужими", async () => {
    await show();
    fireEvent.click(screen.getByText("Финанс-Аудит"));
    await waitFor(() => expect(cardNames()).toContain("Пробный"));
    expect(cardNames()).toEqual(["Пробный", "Команда", "Корпоративный"]);
  });
});
