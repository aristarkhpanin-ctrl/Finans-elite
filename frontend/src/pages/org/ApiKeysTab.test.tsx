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
const getApiKeyScope = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getApiKeys: (...a: unknown[]) => getApiKeys(...a),
  createApiKey: (...a: unknown[]) => createApiKey(...a),
  revokeApiKey: (...a: unknown[]) => revokeApiKey(...a),
  getApiKeyScope: (...a: unknown[]) => getApiKeyScope(...a),
}));

const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));

const key = (over: Partial<ApiKey> = {}): ApiKey => ({
  id: "k1", name: "Выгрузка в BI", masked: "fe_1a2b3c4d_…",
  created_by: "o@e.ru", created_at: "2026-09-01T10:00:00Z",
  last_used_at: null, revoked: false, revoked_at: null, revoked_by: "",
  scopes: ["project.calculate", "project.read"], writes: false, author_gone: false,
  ...over,
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
  getApiKeyScope.mockResolvedValue({
    always: ["project.calculate", "project.read"],
    grantable: ["project.create", "project.update"],
    note: "Право создавать и править модели выдаётся при выпуске: такие правки записаны "
          + "на того, кто выпустил ключ, и ключ перестаёт работать, когда этот человек "
          + "уходит из организации.",
  });
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

it("называет и то, что ключу можно выдать, и то, чего нельзя никогда", async () => {
  show();
  expect(await screen.findByText(/выдать право править модели/)).toBeTruthy();
  expect(screen.getByText(/Удалять модели и писать в обсуждении ключом нельзя/))
    .toBeTruthy();
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

// --- Права выбираются при выпуске (OPEN-DECISIONS §3) ---

it("по умолчанию выпускается читающий ключ", async () => {
  // Ключ живёт в чужом сервере: умолчание обязано быть тем, о чём не пожалеют.
  show();
  fireEvent.change(await screen.findByLabelText("Имя нового ключа"),
                   { target: { value: "Новый" } });
  fireEvent.click(screen.getByRole("button", { name: "Выпустить ключ" }));
  await waitFor(() => expect(createApiKey).toHaveBeenCalledWith("o1", "Новый", []));
});

it("право на запись выдаётся явно — и рядом сказано, чем это обернётся", async () => {
  show();
  const box = await screen.findByRole("checkbox");
  // Последствия названы там же, где выбор, и приходят с сервера: переписанные здесь,
  // они однажды разошлись бы с тем, что платформа делает на самом деле.
  expect(screen.getByText(/уходит из организации/)).toBeTruthy();

  fireEvent.click(box);
  fireEvent.change(screen.getByLabelText("Имя нового ключа"),
                   { target: { value: "Обмен с 1С" } });
  fireEvent.click(screen.getByRole("button", { name: "Выпустить ключ" }));
  await waitFor(() => expect(createApiKey).toHaveBeenCalledWith(
    "o1", "Обмен с 1С", ["project.create", "project.update"]));
});

it("в списке видно, читает ключ или правит", async () => {
  getApiKeys.mockResolvedValue([key({ writes: true })]);
  show();
  expect(await screen.findByText("чтение и запись")).toBeTruthy();
});

it("ключ без автора назван неработающим, а не показан живым", async () => {
  // Живая строка означала бы, что интеграция цела, а она стоит.
  getApiKeys.mockResolvedValue([key({ author_gone: true })]);
  show();
  expect(await screen.findByText(/Не работает/)).toBeTruthy();
  expect(screen.getByText(/выпустите его заново/)).toBeTruthy();
});


it("без права на управление ключи видно, но не заводятся", async () => {
  show(false);
  expect(await screen.findByText("Выгрузка в BI")).toBeTruthy();
  expect(screen.queryByLabelText("Имя нового ключа")).toBeNull();
  expect(screen.getByText(/может владелец организации/)).toBeTruthy();
});
