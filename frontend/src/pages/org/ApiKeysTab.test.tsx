// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ApiKey } from "../../api/org";
import { ApiKeysTab } from "./ApiKeysTab";

/**
 * Ключи доступа (D5). Проверяется то, ради чего экран и сделан: секрет показывается
 * один раз и говорит об этом **до** закрытия окна, отозванный ключ не исчезает из
 * списка, а «ни разу не использован» не выдаётся за «давно».
 */

const getApiKeys = vi.fn();
const createApiKey = vi.fn();
const revokeApiKey = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getApiKeys: (...a: unknown[]) => getApiKeys(...a),
  createApiKey: (...a: unknown[]) => createApiKey(...a),
  revokeApiKey: (...a: unknown[]) => revokeApiKey(...a),
}));

const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));

const key = (over: Partial<ApiKey> = {}): ApiKey => ({
  id: "k1", name: "Выгрузка в BI", masked: "fe_1a2b3c4d_…",
  created_by: "o@e.ru", created_at: "2026-09-01T10:00:00Z",
  last_used_at: null, revoked: false, revoked_at: null, revoked_by: "", ...over,
} as ApiKey);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getApiKeys.mockResolvedValue([key()]);
  createApiKey.mockResolvedValue({
    key: key({ id: "k2", name: "Новый" }),
    token: "fe_9f8e7d6c_секретная-часть",
    scope_note: "Ключ читает данные организации. Изменять модели ключом нельзя.",
  });
  revokeApiKey.mockResolvedValue(key({ revoked: true, revoked_by: "o@e.ru" }));
});

function show(canManage = true) {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <ApiKeysTab orgId="o1" canManage={canManage} />
    </QueryClientProvider>,
  );
}

it("говорит, что ключом нельзя писать, а не только что можно читать", async () => {
  show();
  expect(await screen.findByText(/Изменять модели ключом нельзя/)).toBeTruthy();
});

it("секрет показывается один раз — и об этом сказано до закрытия окна", async () => {
  show();
  fireEvent.change(await screen.findByLabelText("Имя нового ключа"),
                   { target: { value: "Новый" } });
  fireEvent.click(screen.getByRole("button", { name: "Выпустить ключ" }));

  const field = await screen.findByLabelText("Ключ доступа");
  expect((field as HTMLTextAreaElement).value).toBe("fe_9f8e7d6c_секретная-часть");
  // «Покажите ещё раз» невозможно ни для кого, включая поддержку, — и это напечатано.
  expect(screen.getByText(/ни вам, ни поддержке/)).toBeTruthy();
});

it("«ни разу не использован» — это не «давно»", async () => {
  show();
  // Забытый ключ отзывают, а не берегут: состояния обязаны различаться на экране.
  expect(await screen.findByText(/ни разу не использован/)).toBeTruthy();
});

it("отозванный ключ остаётся в списке с отметкой", async () => {
  getApiKeys.mockResolvedValue([key({ revoked: true, revoked_by: "o@e.ru" })]);
  show();
  expect(await screen.findByText("отозван")).toBeTruthy();
  expect(screen.getByText(/отозвал o@e.ru/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Отозвать" })).toBeNull();
});

it("отзыв предупреждает, что всё на этом ключе остановится сразу", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Отозвать" }));
  const dialog = within(screen.getByRole("dialog"));
  expect(dialog.getByText(/остановится/)).toBeTruthy();
  fireEvent.click(dialog.getByRole("button", { name: "Отозвать" }));
  await waitFor(() => expect(revokeApiKey).toHaveBeenCalledWith("o1", "k1"));
});

it("без права на управление ключи видно, но не заводятся", async () => {
  show(false);
  expect(await screen.findByText("Выгрузка в BI")).toBeTruthy();
  expect(screen.queryByLabelText("Имя нового ключа")).toBeNull();
  expect(screen.getByText(/может владелец организации/)).toBeTruthy();
});
