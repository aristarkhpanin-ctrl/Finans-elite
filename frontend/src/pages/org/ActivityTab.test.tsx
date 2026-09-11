// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Activity } from "../../api/org";
import { ActivityTab } from "./ActivityTab";

/**
 * Активность организации (E1). Проверяется то, ради чего оговорки и написаны: пустая
 * отметка присутствия показывается как «нет данных», а не как «никогда», и границы
 * сводки видны рядом с числами.
 */

const getActivity = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getActivity: (...a: unknown[]) => getActivity(...a),
}));

const answer = (over: Partial<Activity> = {}): Activity => ({
  window_days: 30,
  stale_days: 90,
  members: [
    { user_id: "u1", email: "o@e.ru", full_name: "Владелец", role: "owner",
      blocked: false, last_seen_at: "2026-09-10T08:00:00Z", actions: 12 },
    { user_id: "u2", email: "k@e.ru", full_name: "Коллега", role: "editor",
      blocked: false, last_seen_at: null, actions: 0 },
  ],
  entities: [
    { id: "p1", name: "Кофейня", kind: "project", updated_at: "2026-09-09T10:00:00Z",
      last_calculated_at: "2026-09-09T10:05:00Z", stale: false, open_comments: 2 },
    { id: "p2", name: "Старый", kind: "project", updated_at: "2026-01-01T10:00:00Z",
      last_calculated_at: null, stale: true, open_comments: 0 },
  ],
  notes: ["Просмотры журнал не пишет, поэтому ноль означает «ничего не менял».",
          "Расчётов платформа не считает — известна только дата последнего."],
  ...over,
} as Activity);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getActivity.mockResolvedValue(answer());
});

function show() {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })}>
      <ActivityTab orgId="o1" />
    </QueryClientProvider>,
  );
}

it("показывает, кто работает и сколько наменял за окно", async () => {
  show();
  // «Владелец» встречается дважды — именем участника и подписью роли: берём почту.
  expect(await screen.findByText("o@e.ru")).toBeTruthy();
  expect(screen.getByText("12")).toBeTruthy();
  // Окно названо числом: «действий 12» без него — это «за всё время» или «за месяц»?
  expect(screen.getByText(/за последние 30 дн/)).toBeTruthy();
});

it("пустая отметка присутствия — «нет данных», а не «никогда»", async () => {
  show();
  expect(await screen.findByText("нет данных")).toBeTruthy();
});

it("спящую сущность помечает и считает", async () => {
  show();
  expect(await screen.findByText("спит")).toBeTruthy();
  expect(screen.getByText(/не трогали дольше 90 дн/)).toBeTruthy();
});

it("границы сводки показаны рядом с числами", async () => {
  // Без них «действий 0» читается как «бездельничает», а платформа этого не знает.
  show();
  expect(await screen.findByText(/Просмотры журнал не пишет/)).toBeTruthy();
  expect(screen.getByText(/Расчётов платформа не считает/)).toBeTruthy();
});

it("непосчитанное не выдаётся за посчитанное", async () => {
  show();
  // Ждём данных: без этого проверка смотрит на пустой экран и «не находит» что угодно.
  await screen.findByText("Кофейня");
  const dashes = screen.getAllByText("—");
  expect(dashes.length).toBeGreaterThan(0);
});
