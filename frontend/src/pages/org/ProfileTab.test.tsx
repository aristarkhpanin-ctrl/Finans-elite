// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { SessionRow } from "../../api/auth";
import { ProfileTab } from "./ProfileTab";

/**
 * Входы в учётную запись (ADMIN-DECOMPOSITION.md, C1).
 *
 * Проверяется то, что легко потерять при правке экрана: текущий вход помечен и не
 * закрывается кнопкой (иначе человек закроет себя, не поняв как), а список назван
 * подсказкой, а не доказательством — знакомая строка браузера иначе читается как «это
 * точно был я».
 */

const getSessions = vi.fn();
const getPasswordPolicy = vi.fn();
const getTotpStatus = vi.fn();
const startTotpSetup = vi.fn();
const enableTotp = vi.fn();
const revokeSession = vi.fn();
const revokeAllSessions = vi.fn();
const getDeletionPlan = vi.fn();
const deleteMyAccount = vi.fn();
const downloadMyData = vi.fn();
const getCapabilities = vi.fn();
vi.mock("../../api/auth", async (orig) => ({
  ...(await orig<typeof import("../../api/auth")>()),
  getSessions: (...a: unknown[]) => getSessions(...a),
  getPasswordPolicy: (...a: unknown[]) => getPasswordPolicy(...a),
  getTotpStatus: (...a: unknown[]) => getTotpStatus(...a),
  startTotpSetup: (...a: unknown[]) => startTotpSetup(...a),
  enableTotp: (...a: unknown[]) => enableTotp(...a),
  revokeSession: (...a: unknown[]) => revokeSession(...a),
  revokeAllSessions: (...a: unknown[]) => revokeAllSessions(...a),
  getDeletionPlan: (...a: unknown[]) => getDeletionPlan(...a),
  deleteMyAccount: (...a: unknown[]) => deleteMyAccount(...a),
  downloadMyData: (...a: unknown[]) => downloadMyData(...a),
  getCapabilities: (...a: unknown[]) => getCapabilities(...a),
}));

const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));
vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", email: "o@e.ru", full_name: "Владелец" } }),
}));

const session = (over: Partial<SessionRow> = {}): SessionRow => ({
  id: "s1", device: "Chrome · Windows", user_agent: "Mozilla/5.0 …", ip: "203.0.113.7",
  created_at: "2026-09-10T08:00:00Z", last_seen_at: new Date().toISOString(),
  expires_at: "2026-10-10T08:00:00Z", current: false, ...over,
} as SessionRow);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getSessions.mockResolvedValue([
    session({ id: "s1", current: true }),
    session({ id: "s2", device: "Safari · iPhone", ip: "198.51.100.4", current: false }),
  ]);
  revokeSession.mockResolvedValue(undefined);
  getPasswordPolicy.mockResolvedValue({
    min_length: 8, leak_check: false,
    rules: ["Не короче 8 символов.", "Заглавные буквы и знаки препинания **не требуются**."],
  });
  revokeAllSessions.mockResolvedValue(2);
  getTotpStatus.mockResolvedValue({ enabled: false, pending: false, recovery_left: 0,
                                    recommended: true });
  startTotpSetup.mockResolvedValue({
    secret: "ABCDEFGHIJKLMNOP", secret_grouped: "ABCD EFGH IJKL MNOP",
    otpauth_uri: "otpauth://totp/Финанс:o@e.ru?secret=ABCDEFGHIJKLMNOP",
  });
  enableTotp.mockResolvedValue(["AAAAA-BBBBB-CCCCC-DDDDD", "EEEEE-FFFFF-GGGGG-HHHHH"]);
  getDeletionPlan.mockResolvedValue({
    allowed: true, organizations_deleted: ["Орг"], organizations_left: [],
    projects: 3, cases: 1, blockers: [],
    kept: ["Записи журнала в организациях, где вы работали."],
  });
  getCapabilities.mockResolvedValue({ mail: false });
  deleteMyAccount.mockResolvedValue({ allowed: true, organizations_deleted: ["Орг"],
                                      organizations_left: [], projects: 3, cases: 1,
                                      blockers: [], kept: [] });
});

function show() {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <ProfileTab />
    </QueryClientProvider>,
  );
}

it("показывает действующие входы и помечает текущий", async () => {
  show();
  expect(await screen.findByText("Safari · iPhone")).toBeTruthy();
  expect(screen.getByText("этот вход")).toBeTruthy();
  expect(screen.getByText(/203.0.113.7/)).toBeTruthy();
});

it("текущий вход нельзя закрыть кнопкой — иначе человек закроет себя", async () => {
  show();
  await screen.findByText("Safari · iPhone");
  // Кнопка «Закрыть» ровно одна — у чужого входа, не у своего.
  expect(screen.getAllByRole("button", { name: "Закрыть" })).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
  await waitFor(() => expect(revokeSession).toHaveBeenCalledWith("s2"));
});

it("список назван подсказкой, а не доказательством", async () => {
  show();
  await screen.findByText("Safari · iPhone");
  expect(screen.getByText(/можно подделать/)).toBeTruthy();
  // И сказано, где искать историю: второй её копии на этом экране нет.
  expect(screen.getByText(/журнале организации/)).toBeTruthy();
});

it("«выйти на всех устройствах» говорит, сколько входов закрыто", async () => {
  show();
  await screen.findByText("Safari · iPhone");
  fireEvent.click(screen.getByRole("button", { name: "Выйти на всех устройствах" }));
  await waitFor(() => expect(revokeAllSessions).toHaveBeenCalled());
  expect(toast).toHaveBeenCalledWith(expect.stringContaining("Закрыто входов: 2"),
                                     { kind: "success" });
});

it("смена пароля предупреждает, что закроет остальные входы", async () => {
  show();
  expect(await screen.findByText(/закроет остальные входы/)).toBeTruthy();
});


it("требования к паролю берёт с сервера, а не пишет свои", async () => {
  show();
  // Список, перечисленный в интерфейсе своим текстом, однажды разошёлся бы с проверкой:
  // человек прочёл бы одно, а получил другое.
  expect(await screen.findByText(/Заглавные буквы и знаки препинания/)).toBeTruthy();
  expect(getPasswordPolicy).toHaveBeenCalled();
});


// --- C2: второй фактор ---

it("настройка второго фактора честно говорит, что QR-кода нет", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Настроить" }));
  // Спрятанное неудобство человек всё равно обнаружит — только позже и злее.
  expect(await screen.findByText(/QR-кода здесь нет/)).toBeTruthy();
  expect(screen.getByText("ABCD EFGH IJKL MNOP")).toBeTruthy();
});

it("резервные коды показываются один раз и говорят об этом", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Настроить" }));
  fireEvent.change(await screen.findByLabelText("Код из приложения"),
                   { target: { value: "123456" } });
  fireEvent.click(screen.getByRole("button", { name: "Включить" }));

  expect(await screen.findByText("AAAAA-BBBBB-CCCCC-DDDDD")).toBeTruthy();
  expect(screen.getByText(/Больше они не покажутся/)).toBeTruthy();
  // И названа причина: письмо восстанавливает **пароль**, а не второй фактор — иначе
  // доступ к ящику отменял бы второй фактор целиком (D1).
  expect(screen.getByText(/а не второй фактор/)).toBeTruthy();
});

it("владельцу второй фактор рекомендуют, а не навязывают", async () => {
  show();
  expect(await screen.findByText(/Вы владелец организации/)).toBeTruthy();
  // Кнопка «Настроить» — предложение; вход без второго фактора работает (тест бэкенда).
  expect(screen.getByRole("button", { name: "Настроить" })).toBeTruthy();
});

it("выключение спрашивает пароль, а не только открытую вкладку", async () => {
  getTotpStatus.mockResolvedValue({ enabled: true, pending: false, recovery_left: 7,
                                    recommended: true });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Выключить" }));
  const dialog = within(screen.getByRole("dialog"));
  expect(dialog.getByLabelText("Ваш пароль")).toBeTruthy();
  expect((dialog.getByRole("button", { name: "Подтвердить" }) as HTMLButtonElement)
    .disabled).toBe(true);
});


// --- C3: свои данные ---

it("выгрузка названа файлом о человеке, а не о компании", async () => {
  show();
  // Проекты и дела принадлежат организации: отдать их «по запросу субъекта
  // персональных данных» значило бы выдать уходящему модели работодателя.
  expect(await screen.findByText(/Проектов и дел в ней нет/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Выгрузить мои данные" }));
  await waitFor(() => expect(downloadMyData).toHaveBeenCalled());
});

it("удаление показывает последствия до нажатия", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Удалить учётную запись" }));
  const dialog = within(screen.getByRole("dialog"));
  // Вместе с человеком исчезает организация со всеми моделями — это должно быть
  // названо числом, а не общими словами: иначе согласие не осознанное.
  expect(await dialog.findByText(/проектов 3, дел 1/)).toBeTruthy();
  expect(dialog.getByText(/Записи журнала/)).toBeTruthy();
});

it("удаление требует пароль, а не только открытую вкладку", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Удалить учётную запись" }));
  const dialog = within(screen.getByRole("dialog"));
  const submit = await dialog.findByRole("button", { name: "Удалить навсегда" });
  expect((submit as HTMLButtonElement).disabled).toBe(true);

  fireEvent.change(dialog.getByLabelText("Ваш пароль"), { target: { value: "parol" } });
  fireEvent.click(submit);
  await waitFor(() => expect(deleteMyAccount).toHaveBeenCalledWith("parol"));
});

it("владельцу с коллегами отказывают и называют выход", async () => {
  getDeletionPlan.mockResolvedValue({
    allowed: false, organizations_deleted: [], organizations_left: [],
    projects: 0, cases: 0,
    blockers: ["Вы владелец организации «Орг», в ней ещё 2 чел. Передайте владение "
               + "другому участнику — или удалите их из организации."],
    kept: [],
  });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Удалить учётную запись" }));
  const dialog = within(screen.getByRole("dialog"));
  expect(await dialog.findByText(/Передайте владение/)).toBeTruthy();
  // Кнопка не прячется — отказ объяснён, а не изображён отсутствием возможности.
  expect((dialog.getByRole("button", { name: "Удалить навсегда" }) as HTMLButtonElement)
    .disabled).toBe(true);
  expect(dialog.queryByLabelText("Ваш пароль")).toBeNull();
});


// --- D1: почта ---

it("без почты экран не обещает писем о новых входах", async () => {
  // «Мы предупредим» в установке без почты — обещание, которое некому выполнить.
  show();
  expect(await screen.findByText(/Писем о новых входах платформа не шлёт/)).toBeTruthy();
});

it("с почтой обещание даётся — и оно выполняется сервером", async () => {
  getCapabilities.mockResolvedValue({ mail: true });
  show();
  expect(await screen.findByText(/О входе с незнакомого устройства/)).toBeTruthy();
});
