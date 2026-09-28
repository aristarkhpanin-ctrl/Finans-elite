// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ChecklistsTab } from "./ChecklistsTab";

/**
 * Свои чек-листы организации (D4). Главное, что проверяется, — отказ, оставшийся в
 * силе: платформа не утверждает, что именно проверяют в отрасли, и экран говорит это
 * словами, а не умалчивает.
 */

const getChecklists = vi.fn();
const putChecklists = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getChecklists: (...a: unknown[]) => getChecklists(...a),
  putChecklists: (...a: unknown[]) => putChecklists(...a),
}));
const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getChecklists.mockResolvedValue([]);
  putChecklists.mockResolvedValue([]);
});

function show(canManage = true) {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <ChecklistsTab orgId="o1" canManage={canManage} />
    </QueryClientProvider>,
  );
}

it("говорит, что отраслевого каталога у платформы нет", async () => {
  show();
  expect(await screen.findByText(/Отраслевого каталога у платформы/)).toBeTruthy();
  expect(screen.getByText(/платформа их не выполняет/)).toBeTruthy();
});

it("пустой список зовёт завести первый и называет пользу", async () => {
  show();
  expect(await screen.findByText(/перестанете\s+перепечатывать/)).toBeTruthy();
});

it("чек-лист заводится и сохраняется целиком", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: /Чек-лист/ }));
  fireEvent.change(screen.getByLabelText("Название"),
                   { target: { value: "Производство" } });
  fireEvent.change(screen.getByLabelText("Процедуры чек-листа 1"),
                   { target: { value: "Осмотреть площадку\nСверить склад" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(putChecklists).toHaveBeenCalledWith("o1", [
    { name: "Производство", scope: "", items: ["Осмотреть площадку", "Сверить склад"] },
  ]));
});

it("без права на правку чек-листы видно, но не меняются", async () => {
  getChecklists.mockResolvedValue([
    { id: "c1", name: "Базовый", scope: "", items: ["раз"], author_email: "o@e.ru",
      updated_at: "2026-09-01T10:00:00Z" },
  ]);
  show(false);
  expect(await screen.findByDisplayValue("Базовый")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
  expect(screen.getByText(/Применять их к делам может/)).toBeTruthy();
});
