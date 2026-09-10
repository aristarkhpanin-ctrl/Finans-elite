// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { StaffOrg, StaffOrgDetail, StaffUser } from "../api/admin";
import { AdminPage } from "./AdminPage";

/**
 * Служебный раздел платформы (ADMIN-DECOMPOSITION.md, B1).
 *
 * Проверяется не «экран рисуется», а обещания, которые легко потерять при правке: раздел
 * закрыт для не-сотрудника и **объясняет** отказ; оператору сказано, что его визит
 * записан в журнал клиента; отсутствующее названо отсутствующим (счётчика расчётов нет,
 * подписка не оформлялась). Оговорка о визите — не украшение: убранная как «шум», она
 * превращает наблюдение в слежку, о которой сам наблюдающий не подозревает.
 *
 * Границу «содержимого моделей не запрашиваем» стережёт `api/admin.test.ts`: экранная
 * проверка сводилась бы к тому, что мы не нарисовали неприсланного.
 */

const getStaffOrganizations = vi.fn();
const getStaffOrganization = vi.fn();
const getStaffOrgLog = vi.fn();
const searchStaffUsers = vi.fn();
const getStaffLog = vi.fn();
vi.mock("../api/admin", () => ({
  getStaffOrganizations: (...a: unknown[]) => getStaffOrganizations(...a),
  getStaffOrganization: (...a: unknown[]) => getStaffOrganization(...a),
  getStaffOrgLog: (...a: unknown[]) => getStaffOrgLog(...a),
  searchStaffUsers: (...a: unknown[]) => searchStaffUsers(...a),
  getStaffLog: (...a: unknown[]) => getStaffLog(...a),
}));

let staff = true;
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", email: "s@e.ru", full_name: "С", is_staff: staff } }),
}));

const org = (over: Partial<StaffOrg> = {}): StaffOrg => ({
  id: "o1", name: "ООО «Клиент»", created_at: "2026-01-15T10:00:00Z",
  members: 3, members_blocked: 1, projects: 4, cases: 2, groups: 0, holdings: 0,
  last_calculated_at: null, last_seen_at: "2026-09-09T09:00:00Z",
  subscriptions: [
    { product: "business", plan_code: "pro", plan_name: "Профи", status: "active",
      current_period_end: null },
    { product: "audit", plan_code: "free", plan_name: "Бесплатный", status: "none",
      current_period_end: null },
  ],
  ...over,
} as StaffOrg);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  staff = true;
  getStaffOrganizations.mockResolvedValue({ organizations: [org()], total: 1 });
  getStaffOrganization.mockResolvedValue({
    ...org(),
    members_list: [{ user_id: "u9", email: "k@e.ru", full_name: "Коллега", role: "analyst",
                     blocked: true, block_reason: "увольнение", last_seen_at: null }],
  } as unknown as StaffOrgDetail);
  getStaffOrgLog.mockResolvedValue({ entries: [], total: 0, actors: [], actions: [] });
  searchStaffUsers.mockResolvedValue([]);
  getStaffLog.mockResolvedValue({ entries: [] });
});

function show() {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <AdminPage />
    </QueryClientProvider>,
  );
}

it("не-сотруднику объясняет отказ, а не прячет раздел", async () => {
  staff = false;
  show();
  expect(await screen.findByText(/доступен сотрудникам платформы/i)).toBeTruthy();
  expect(getStaffOrganizations).not.toHaveBeenCalled();
});

it("показывает клиента снаружи: тарифы, объёмы, активность", async () => {
  show();
  expect(await screen.findByText("ООО «Клиент»")).toBeTruthy();
  expect(screen.getByText(/Элит: Профи/)).toBeTruthy();
  // «Не оформлял» и «оформил бесплатный» — разные состояния, и подписаны они по-разному.
  expect(screen.getByText(/Аудит: Бесплатный · подписка не оформлялась/)).toBeTruthy();
  expect(screen.getByText(/проектов 4 · дел 2/)).toBeTruthy();
  expect(screen.getByText(/3 уч\. \(1 приост\.\)/)).toBeTruthy();
});

it("оговорка о записи визита стоит на экране", async () => {
  show();
  await screen.findByText("ООО «Клиент»");
  expect(screen.getByText(/записываются в журнал самого клиента/i)).toBeTruthy();
});

it("карточка организации открывается явным действием — открытие и есть визит", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "ООО «Клиент»" }));
  await waitFor(() => expect(getStaffOrganization).toHaveBeenCalledWith("o1"));
  expect(await screen.findByText(/Ваш визит записан в журнал этой организации/i)).toBeTruthy();
  expect(screen.getByText(/приостановлен: увольнение/)).toBeTruthy();
});

it("вместо числа расчётов называет, что счётчика нет", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "ООО «Клиент»" }));
  expect(await screen.findByText(/счётчика расчётов платформа не ведёт/i)).toBeTruthy();
});

it("поиск человека различает «пароль не заводился» и «доступ приостановлен»", async () => {
  searchStaffUsers.mockResolvedValue([{
    id: "u9", email: "k@e.ru", full_name: "Коллега", created_at: "2026-02-01T00:00:00Z",
    is_staff: false, has_password: false,
    organizations: [{ id: "o1", name: "ООО «Клиент»", role: "analyst", blocked: true,
                      block_reason: "увольнение", last_seen_at: null }],
  } as StaffUser]);
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Пользователи" }));
  expect(await screen.findByText("Коллега")).toBeTruthy();
  expect(screen.getByText("не заводился")).toBeTruthy();
  expect(screen.getByText(/приостановлен: увольнение/)).toBeTruthy();
});

it("служебный журнал показывает, где были сотрудники", async () => {
  getStaffLog.mockResolvedValue({ entries: [{
    id: "l1", actor_email: "s@e.ru", action: "staff.org_view", organization_id: "o1",
    organization_name: "ООО «Клиент»", details: "", created_at: "2026-09-10T08:00:00Z",
  }] });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Журнал сотрудников" }));
  expect(await screen.findByText("staff.org_view")).toBeTruthy();
  expect(screen.getByText("ООО «Клиент»")).toBeTruthy();
});
