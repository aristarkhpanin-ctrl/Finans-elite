// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { SupportAccess, SupportGrant } from "../../api/org";
import { SupportAccessTab } from "./SupportAccessTab";

/**
 * Доступ поддержки к моделям организации (F4).
 *
 * Проверяется то, ради чего экран и сделан: платформа своих моделей клиента не видит,
 * пока он не открыл дверь; охват гранта и его односторонность названы **до** нажатия;
 * срок показан числом, а не «скоро»; закрытые доступы остаются в истории, потому что
 * «нам никто не открывал» — проверяемое утверждение, а не отсутствие записи.
 */

const getSupportAccess = vi.fn();
const grantSupportAccess = vi.fn();
const revokeSupportAccess = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getSupportAccess: (...a: unknown[]) => getSupportAccess(...a),
  grantSupportAccess: (...a: unknown[]) => grantSupportAccess(...a),
  revokeSupportAccess: (...a: unknown[]) => revokeSupportAccess(...a),
}));

const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));

const NOTES = [
  "Доступ открывается ко **всем** проектам и делам организации, а не к одному. "
  + "Каждое обращение сотрудника платформы к вашим числам попадает в журнал организации.",
  "Сотрудник платформы может только смотреть: правка, удаление и расчёт от вашего "
  + "имени грантом не открываются.",
];

const grant = (over: Partial<SupportGrant> = {}): SupportGrant => ({
  id: "g1", granted_by_email: "owner@e.ru", reason: "не считается проект",
  created_at: "2026-09-20T08:00:00Z",
  expires_at: new Date(Date.now() + 5 * 3_600_000).toISOString(),
  revoked_at: null, active: true, ...over,
} as SupportGrant);

const state = (over: Partial<SupportAccess> = {}): SupportAccess => ({
  current: null, history: [], max_hours: 72, notes: NOTES, ...over,
} as SupportAccess);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getSupportAccess.mockResolvedValue(state());
  grantSupportAccess.mockResolvedValue(state({ current: grant(), history: [grant()] }));
  revokeSupportAccess.mockResolvedValue(state({
    history: [grant({ active: false, revoked_at: "2026-09-20T10:00:00Z" })] }));
});

function show(canManage = true) {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <SupportAccessTab orgId="o1" canManage={canManage} />
    </QueryClientProvider>,
  );
}

it("по умолчанию доступ закрыт, и это сказано прямо", async () => {
  show();
  expect(await screen.findByText(/содержимое ваших моделей платформе не видно/i)).toBeTruthy();
});

it("экран говорит, что платформа не может открыть доступ себе сама", async () => {
  // Это и есть суть ограничения: правило не отменено, у него появился ключ — и ключ
  // у клиента. Без этой фразы экран читается как «платформа решила нас пустить».
  show();
  expect(await screen.findByText(/открыть его себе не может/i)).toBeTruthy();
});

it("охват гранта назван до нажатия, а не после", async () => {
  // Сузить доступ до одной модели платформа не умеет, и делать вид, что умеет, хуже.
  show();
  expect(await screen.findByText(/ко \*\*всем\*\* проектам и делам|ко всем проектам и делам/))
    .toBeTruthy();
  expect(screen.getByText(/только смотреть/)).toBeTruthy();
});

it("причина обязательна: без неё кнопка не работает", async () => {
  show();
  const open = await screen.findByRole("button", { name: "Открыть доступ" });
  expect((open as HTMLButtonElement).disabled).toBe(true);

  fireEvent.change(screen.getByLabelText("Зачем"),
                   { target: { value: "не считается проект" } });
  expect((screen.getByRole("button", { name: "Открыть доступ" }) as HTMLButtonElement)
    .disabled).toBe(false);
});

it("открытый доступ показывает остаток срока числом, а не «скоро»", async () => {
  getSupportAccess.mockResolvedValue(state({ current: grant(), history: [grant()] }));
  show();
  expect(await screen.findByText(/осталось \d+ ч/)).toBeTruthy();
  expect(screen.getByText(/не считается проект/)).toBeTruthy();
});

it("предел срока берётся с сервера, а не пишется здесь второй раз", async () => {
  // Обе надписи — объяснение сверху и подсказка у поля — идут из одного числа. Вписанный
  // сюда «72» однажды разошёлся бы с сервером, и экран обещал бы срок, которого нет.
  getSupportAccess.mockResolvedValue(state({ max_hours: 48 }));
  show();
  expect((await screen.findAllByText(/не больше 48 ч/i)).length).toBe(2);
});

it("выдача отправляет часы и причину", async () => {
  show();
  fireEvent.change(await screen.findByLabelText("Зачем"),
                   { target: { value: "не считается проект" } });
  fireEvent.change(screen.getByLabelText("На сколько часов"), { target: { value: "8" } });
  fireEvent.click(screen.getByRole("button", { name: "Открыть доступ" }));

  await waitFor(() => expect(grantSupportAccess)
    .toHaveBeenCalledWith("o1", 8, "не считается проект"));
});

it("оговорка об обрезанном сроке показывается, а не глотается", async () => {
  // Обрезать и промолчать значило бы показать «до пятницы» там, где доступ кончится
  // в среду.
  grantSupportAccess.mockResolvedValue(state({
    current: grant(), history: [grant()],
    notes: ["Срок сокращён до 72 ч: дольше платформа доступ не держит.", ...NOTES] }));
  show();
  fireEvent.change(await screen.findByLabelText("Зачем"), { target: { value: "разбор" } });
  fireEvent.click(screen.getByRole("button", { name: "Открыть доступ" }));

  expect(await screen.findByText(/Срок сокращён до 72 ч/)).toBeTruthy();
});

it("закрытый доступ остаётся в истории", async () => {
  // «Нам никто не открывал» должно быть проверяемым утверждением.
  getSupportAccess.mockResolvedValue(state({
    history: [grant({ active: false, revoked_at: "2026-09-20T10:00:00Z" })] }));
  show();
  expect(await screen.findByText("Раньше открывали")).toBeTruthy();
  expect(screen.getByText("закрыт")).toBeTruthy();
});

it("без права на управление состояние видно, а кнопок нет", async () => {
  // «Кто пустил платформу в наши числа» — не секрет от тех, чьи это числа.
  getSupportAccess.mockResolvedValue(state({ current: grant(), history: [grant()] }));
  show(false);
  expect(await screen.findByText(/Доступ открыт/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Закрыть доступ" })).toBeNull();
  expect(screen.getByText(/владелец или администратор/i)).toBeTruthy();
});

it("закрытие предупреждает, что запись о доступе останется", async () => {
  getSupportAccess.mockResolvedValue(state({ current: grant(), history: [grant()] }));
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Закрыть доступ" }));
  expect(await screen.findByText(/Запись о том, что доступ был открыт, останется/))
    .toBeTruthy();
});
