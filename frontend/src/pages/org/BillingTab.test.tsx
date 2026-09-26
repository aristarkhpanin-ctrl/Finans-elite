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
const checkout = vi.fn();
const changePlan = vi.fn();
const getQuote = vi.fn();
const disableAutoRenew = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getPlans: (...a: unknown[]) => getPlans(...a),
  getSubscription: (...a: unknown[]) => getSubscription(...a),
  checkout: (...a: unknown[]) => checkout(...a),
  changePlan: (...a: unknown[]) => changePlan(...a),
  getQuote: (...a: unknown[]) => getQuote(...a),
  disableAutoRenew: (...a: unknown[]) => disableAutoRenew(...a),
}));
const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  checkout.mockResolvedValue({ activated: true, confirmation_url: null });
  changePlan.mockResolvedValue({});
  disableAutoRenew.mockResolvedValue({});
  getQuote.mockImplementation((_o: string, code: string, months: number) => Promise.resolve({
    plan_code: code, plan_name: "Команда", months,
    amount_rub: months === 12 ? 31320 : 2900, full_price_rub: 2900 * months,
    discount_percent: months === 12 ? 10 : 0, starts_at: "2026-09-20T00:00:00Z",
    ends_at: months === 12 ? "2027-09-15T00:00:00Z" : "2026-10-20T00:00:00Z",
    continues: false, lost_days: 0, auto_renew_available: true,
    auto_renew_unavailable_reason: "",
  }));
});

const BUSINESS_PLANS: Plan[] = [
  { code: "free", product: "business", name: "Бесплатный", price_rub: 0,
    price_on_request: false, max_units: 5, unit_name: "проектов", max_members: 5 },
  { code: "team", product: "business", name: "Команда", price_rub: 2900,
    price_on_request: false, max_units: 50, unit_name: "проектов", max_members: 25,
    annual_price_rub: 31320, annual_discount_percent: 10 },
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
        max_members: 5, used_units: 1, used_members: 1, auto_renew: false,
        auto_renew_available: true, auto_renew_unavailable_reason: "",
        renew_error: "" } as Subscription;
}

async function show(over: Partial<Subscription> = {}) {
  getPlans.mockImplementation((p: string) => Promise.resolve(
    p === "audit" ? AUDIT_PLANS : BUSINESS_PLANS));
  getSubscription.mockImplementation((_o: string, p: string) =>
    Promise.resolve({ ...sub(p), ...over } as Subscription));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><BillingTab orgId="o1" canManage /></QueryClientProvider>);
  await screen.findByText("Тарифные планы");
}

/** Текст без неразрывных пробелов: суммы «2 900 ₽» форматируются через ru-RU. */
const plain = (el: Element | null) => (el?.textContent ?? "").replace(/\u00a0/g, " ");

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

/**
 * Две дороги к тарифу, и они не взаимозаменяемы (F1). Платный включает **оплата**;
 * понижение идёт своим маршрутом — платёж на ноль рублей это не платёж; тариф «по
 * запросу» не берётся ни одной из дорог.
 */
describe("Как меняется тариф", () => {
  const confirm = async (planName: string) => {
    fireEvent.click([...document.querySelectorAll(".plan-card")]
      .find((c) => c.textContent?.includes(planName))!
      .querySelector("button")!);
    fireEvent.click(await screen.findByRole("button", { name: "Подтвердить" }));
  };

  it("платный тариф включается оплатой — за месяц и без согласия по умолчанию", async () => {
    await show();
    await confirm("Команда");
    await waitFor(() => expect(checkout).toHaveBeenCalledWith(
      "o1", "team", { months: 1, autoRenew: false }));
    expect(changePlan).not.toHaveBeenCalled();
  });

  it("понижение на бесплатный идёт своим маршрутом, а не платежом на ноль", async () => {
    await show({ plan_code: "team", plan_name: "Команда", price_rub: 2900,
                 max_units: 50 });
    await confirm("Бесплатный");
    await waitFor(() => expect(changePlan).toHaveBeenCalledWith("o1", "free"));
    expect(checkout).not.toHaveBeenCalled();
  });

  it("у тарифа «по запросу» кнопки нет вовсе", async () => {
    // Кнопка «Запросить», после которой ничего не происходит, хуже её отсутствия:
    // автоматической заявки платформа не отправляет — ящика для входящих у неё нет.
    await show();
    fireEvent.click(screen.getByText("Финанс-Аудит"));
    await waitFor(() => expect(cardNames()).toContain("Корпоративный"));
    const card = [...document.querySelectorAll(".plan-card")]
      .find((c) => c.textContent?.includes("Корпоративный"))!;
    expect(card.querySelector("button")).toBeNull();
    expect(card.textContent).toContain("заявку этот экран не отправляет");
  });
});

describe("Отказ сервера доходит до человека", () => {
  /**
   * Сервер отказывает словами и называет выход: «оплата в продукте не подключена —
   * оплатите по счёту» (G1). Общее «не удалось сменить тариф» съело бы ровно то, что
   * клиенту, готовому платить, нужнее всего.
   */
  const reject = (status: number, detail?: string) => {
    const err = Object.assign(new Error("x"), {
      isAxiosError: true,
      response: { status, data: detail === undefined ? {} : { detail } },
    });
    checkout.mockRejectedValue(err);
  };

  const pick = async (planName: string) => {
    fireEvent.click([...document.querySelectorAll(".plan-card")]
      .find((c) => c.textContent?.includes(planName))!
      .querySelector("button")!);
    fireEvent.click(await screen.findByRole("button", { name: "Подтвердить" }));
  };

  it("причина отказа показывается дословно", async () => {
    reject(503, "Оплата в продукте сейчас не подключена. Тариф можно получить оплатой по счёту.");
    await show();
    await pick("Команда");
    await waitFor(() => expect(toast).toHaveBeenCalledWith(
      "Оплата в продукте сейчас не подключена. Тариф можно получить оплатой по счёту.",
      { kind: "error" }));
  });

  it("без причины остаётся общее сообщение, а не пустой тост", async () => {
    reject(500);
    await show();
    await pick("Команда");
    await waitFor(() => expect(toast).toHaveBeenCalledWith(
      "Не удалось сменить тариф", { kind: "error" }));
  });
});

/**
 * Срок, сумма и согласие (G5). Согласие на автопродление — отдельная отметка, выключенная
 * по умолчанию: деньги клиента не списываются без его явного решения. Сумму и срок
 * называет сервер — у экрана нет своей копии правил скидки и продления.
 */
describe("Оплата: срок и согласие", () => {
  const openPay = async (planName = "Команда") => {
    fireEvent.click([...document.querySelectorAll(".plan-card")]
      .find((c) => c.textContent?.includes(planName))!
      .querySelector("button")!);
    await screen.findByRole("button", { name: "Подтвердить" });
  };

  it("год — со скидкой владельца, и оплата уходит за 12 месяцев", async () => {
    await show();
    await openPay();
    fireEvent.click(screen.getByRole("button", { name: /Год · 31\s320/ }));
    await screen.findByText(/вместо 34\s800\s₽ — скидка 10\s%/);
    expect(getQuote).toHaveBeenLastCalledWith("o1", "team", 12);
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await waitFor(() => expect(checkout).toHaveBeenCalledWith(
      "o1", "team", { months: 12, autoRenew: false }));
  });

  it("согласие отмечается отдельно и называет сумму, на которую даётся", async () => {
    await show();
    await openPay();
    const box = screen.getByRole("checkbox") as HTMLInputElement;
    expect(box.checked).toBe(false);
    expect(plain(box.closest("label"))).toContain("2 900 ₽");
    fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await waitFor(() => expect(checkout).toHaveBeenCalledWith(
      "o1", "team", { months: 1, autoRenew: true }));
  });

  it("отметка не переживает повторного открытия окна", async () => {
    await show();
    await openPay();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    await openPay();
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
  });

  it("где автопродление невозможно, отметка выключена и названа причина", async () => {
    await show({ auto_renew_available: false,
                 auto_renew_unavailable_reason: "Автопродление требует почты." });
    await openPay();
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("Автопродление требует почты.")).toBeTruthy();
  });

  it("срок назван датой, а потерянные дни прежнего тарифа — числом", async () => {
    getQuote.mockResolvedValue({
      plan_code: "team", plan_name: "Команда", months: 1, amount_rub: 2900,
      full_price_rub: 2900, discount_percent: 0, starts_at: "2026-09-20T00:00:00Z",
      ends_at: "2026-10-20T00:00:00Z", continues: false, lost_days: 12,
      auto_renew_available: true, auto_renew_unavailable_reason: "" });
    await show();
    await openPay();
    await screen.findByText(/Будет оплачено до/);
    expect(screen.getByText(/Оставшиеся 12 дн\. тарифа «Бесплатный» не переносятся/))
      .toBeTruthy();
  });
});

describe("Автопродление на карточке тарифа", () => {
  const renewing = {
    plan_code: "team", plan_name: "Команда", price_rub: 2900,
    current_period_end: "2026-10-20T00:00:00Z", auto_renew: true,
    payment_method_title: "MasterCard *4444", renew_months: 1, renew_amount_rub: 2900,
    next_charge_at: "2026-10-19T00:00:00Z",
  } as Partial<Subscription>;

  it("называет сумму, способ и дату, а дату периода — «оплачено до»", async () => {
    await show(renewing);
    const card = plain(document.querySelector(".plan-current"));
    expect(card).toContain("Оплачено до");
    expect(card).not.toContain("Продление");
    expect(card).toContain("2 900 ₽");
    expect(card).toContain("MasterCard *4444");
  });

  it("причина неудачи показывается словами сервера", async () => {
    await show({ ...renewing, renew_error: "Списание не прошло: недостаточно средств." });
    expect(screen.getByText("Списание не прошло: недостаточно средств.")).toBeTruthy();
  });

  it("выключение — через подтверждение, где названы последствия", async () => {
    await show(renewing);
    fireEvent.click(screen.getByRole("button", { name: "Выключить автопродление" }));
    expect(await screen.findByText(/способ\s+оплаты будет забыт/)).toBeTruthy();
    expect(disableAutoRenew).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Выключить" }));
    await waitFor(() => expect(disableAutoRenew).toHaveBeenCalledWith("o1", "business"));
  });
});
