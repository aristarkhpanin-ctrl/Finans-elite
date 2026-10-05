// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Overview, ProductState } from "../../api/org";
import { OverviewTab } from "./OverviewTab";

/**
 * Сводка организации (F7).
 *
 * Проверяется то, ради чего экран и сделан: «без предела» не превращается в ноль,
 * «не истекает» не превращается в «истёк», расчёты не выдумываются, ограничение
 * показано теми же словами, какими отказывает сохранение, и оговорки видны.
 */

const getOverview = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getOverview: (...a: unknown[]) => getOverview(...a),
}));

const product = (over: Partial<ProductState> = {}): ProductState => ({
  product: "business", product_name: "Финанс-Элит", plan_code: "free",
  plan_name: "Бесплатный", status: "active", unit_name: "проектов",
  units_used: 2, units_limit: 5, units_left: 3,
  members_limit: 5, members_left: 4,
  period_end: null, days_left: null, grace_left: null,
  restriction_kind: "", restriction_reason: "", restriction_remedy: "",
  restriction_blocking: false, ...over,
} as ProductState);

const overview = (over: Partial<Overview> = {}): Overview => ({
  name: "ООО «Клиент»", created_at: "2026-01-15T10:00:00Z",
  projects: 2, cases: 1, groups: 0, holdings: 0,
  members: 1, members_blocked: 0, members_unknown: 0,
  last_calculated_at: null, last_seen_at: null,
  products: [product()],
  notes: ["«Считали» платформа не считает: счётчика расчётов нет."],
  ...over,
} as Overview);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getOverview.mockResolvedValue(overview());
});

function show() {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })}>
      <OverviewTab orgId="o1" />
    </QueryClientProvider>,
  );
}

it("показывает объёмы одним взглядом", async () => {
  show();
  const table = within(await screen.findByRole("table", { name: "Объёмы организации" }));
  expect(table.getByText("2")).toBeTruthy();
  expect(screen.getByText(/осталось 3 из 5 проектов/)).toBeTruthy();
});

it("«без предела» не превращается в ноль", async () => {
  // Написать здесь «0» значило бы показать корпоративному клиенту, что ему ничего нельзя.
  getOverview.mockResolvedValue(overview({
    products: [product({ units_limit: null, units_left: null,
                         members_limit: null, members_left: null })] }));
  show();
  expect((await screen.findAllByText("без предела")).length).toBe(2);
  expect(screen.queryByText(/осталось 0/)).toBeNull();
});

it("отсутствие срока названо «не истекает», а не прочерком", async () => {
  show();
  expect(await screen.findByText("тариф не истекает")).toBeTruthy();
});

it("срок показан числом дней, а не «скоро»", async () => {
  getOverview.mockResolvedValue(overview({
    products: [product({ period_end: "2026-10-01T00:00:00Z", days_left: 11 })] }));
  show();
  expect(await screen.findByText(/11 дней/)).toBeTruthy();
});

it("расчёты не выдумываются: пусто — «ещё не считали»", async () => {
  show();
  expect(await screen.findByText("ещё не считали")).toBeTruthy();
});

it("льготный срок — предупреждение, а не отказ, и назван числом", async () => {
  getOverview.mockResolvedValue(overview({
    products: [product({
      grace_left: 11, restriction_kind: "grace", restriction_blocking: false,
      restriction_reason: "Оплаченный период закончился.",
      restriction_remedy: "Оплатите тариф, чтобы не потерять правки." })] }));
  show();
  expect(await screen.findByText(/Льготный срок — 11 дней/)).toBeTruthy();
  expect(screen.queryByText("Изменения закрыты")).toBeNull();
});

it("ограничение показано теми же словами, какими отказывает сохранение", async () => {
  // Второй источник этой правды разошёлся бы с первым, и клиент видел бы спокойный
  // экран, на котором ничего не сохраняется.
  getOverview.mockResolvedValue(overview({
    products: [product({
      status: "past_due", restriction_kind: "unpaid", restriction_blocking: true,
      restriction_reason: "Подписка «Финанс-Элит» не оплачена.",
      restriction_remedy: "Оплатите тариф — доступ вернётся сразу." })] }));
  show();
  expect(await screen.findByText("Изменения закрыты")).toBeTruthy();
  expect(screen.getByText(/не оплачена\. Оплатите тариф/)).toBeTruthy();
  expect(screen.getByText(/просрочена оплата/)).toBeTruthy();
});

it("оговорки показаны, а не спрятаны", async () => {
  getOverview.mockResolvedValue(overview({
    members_unknown: 2,
    notes: ["«Считали» платформа не считает: счётчика расчётов нет.",
            "У 2 из 3 участников нет отметки присутствия — это «неизвестно», а не «не работает»."],
  }));
  show();
  expect(await screen.findByText(/счётчика расчётов нет/)).toBeTruthy();
  expect(screen.getByText(/«неизвестно», а не «не работает»/)).toBeTruthy();
});
