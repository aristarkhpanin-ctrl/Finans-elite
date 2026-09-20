// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { PlatformMetrics, StaffOrg, StaffOrgDetail, StaffUser } from "../api/admin";
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
const getStaffList = vi.fn();
const getStaffJobs = vi.fn();
const getOrgProjects = vi.fn();
const getOrgProject = vi.fn();
const getOrgSubjects = vi.fn();
const getOrgSubject = vi.fn();
const suspendOrganization = vi.fn();
const resumeOrganization = vi.fn();
const blockUser = vi.fn();
const unblockUser = vi.fn();
const getPlatformMetrics = vi.fn();
const downloadMetricsCsv = vi.fn();
const downloadUsageCsv = vi.fn();
const assignPlan = vi.fn();
const getPlans = vi.fn();
vi.mock("../api/admin", () => ({
  getStaffOrganizations: (...a: unknown[]) => getStaffOrganizations(...a),
  getStaffOrganization: (...a: unknown[]) => getStaffOrganization(...a),
  getStaffOrgLog: (...a: unknown[]) => getStaffOrgLog(...a),
  searchStaffUsers: (...a: unknown[]) => searchStaffUsers(...a),
  getStaffLog: (...a: unknown[]) => getStaffLog(...a),
  getStaffList: (...a: unknown[]) => getStaffList(...a),
  getStaffJobs: (...a: unknown[]) => getStaffJobs(...a),
  getOrgProjects: (...a: unknown[]) => getOrgProjects(...a),
  getOrgProject: (...a: unknown[]) => getOrgProject(...a),
  getOrgSubjects: (...a: unknown[]) => getOrgSubjects(...a),
  getOrgSubject: (...a: unknown[]) => getOrgSubject(...a),
  suspendOrganization: (...a: unknown[]) => suspendOrganization(...a),
  resumeOrganization: (...a: unknown[]) => resumeOrganization(...a),
  blockUser: (...a: unknown[]) => blockUser(...a),
  unblockUser: (...a: unknown[]) => unblockUser(...a),
  getPlatformMetrics: (...a: unknown[]) => getPlatformMetrics(...a),
  downloadMetricsCsv: (...a: unknown[]) => downloadMetricsCsv(...a),
  downloadUsageCsv: (...a: unknown[]) => downloadUsageCsv(...a),
  assignPlan: (...a: unknown[]) => assignPlan(...a),
}));

const toast = vi.fn();
vi.mock("../api/org", async (orig) => ({
  ...(await orig<typeof import("../api/org")>()),
  getPlans: (...a: unknown[]) => getPlans(...a),
}));
vi.mock("../components/Toast", () => ({ useToast: () => toast }));

let staff = true;
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", email: "s@e.ru", full_name: "С", is_staff: staff } }),
}));

const person = (over: Partial<StaffUser> = {}): StaffUser => ({
  id: "u9", email: "k@e.ru", full_name: "Коллега", created_at: "2026-02-01T00:00:00Z",
  is_staff: false, has_password: true, blocked: false, blocked_at: null, blocked_by: "",
  block_reason: "", organizations: [], ...over,
} as StaffUser);

const metrics = (over: Partial<PlatformMetrics> = {}): PlatformMetrics => ({
  generated_at: "2026-09-10T08:00:00Z", since_days: 30,
  organizations: 12, users: 30,
  active_users: { "7": 5, "30": 9 }, active_organizations: { "7": 3, "30": 7 },
  members_without_mark: 4, projects: 40, cases: 6,
  projects_calculated: 11, exports: 2,
  growth: [{ period: "2026-08", organizations: 2, users: 5 },
           { period: "2026-09", organizations: 0, users: 0 }],
  plans: [{ product: "business", plan_code: "pro", plan_name: "Профи", organizations: 3 }],
  funnel: [
    { key: "signup", label: "Завели организацию", organizations: 12, share: 1 },
    { key: "created", label: "Завели проект или дело", organizations: 9, share: 0.75 },
    { key: "calculated", label: "Посчитали хотя бы раз", organizations: 6, share: 0.5 },
    { key: "exported", label: "Выгрузили документ", organizations: 2, share: 0.17 },
    { key: "paid", label: "Перешли на платный тариф", organizations: 3, share: 0.25 },
  ],
  retention: [],
  revenue: [{ month: "2026-08", rub: 2900, payments: 1 },
            { month: "2026-09", rub: 0, payments: 0 }],
  // По умолчанию отток **измерен**: ряд с прочерками сделал бы слово «не измеряется»
  // неоднозначным на экране, где его же ищут тесты удержания.
  churn: {
    months: [
      { month: "2026-08", expired: 1, downgraded: 0, payers: 3, stopped: 1, rate: 0.5 },
      { month: "2026-09", expired: 0, downgraded: 0, payers: 2, stopped: 0, rate: 0 },
    ],
    expiry_logged: true, unnamed_plan_changes: 0,
  },
  usage_collected: false,
  notes: ["Журнал ведётся с 01.08.2026 — за более ранние даты выгрузок не видно."],
  ...over,
} as PlatformMetrics);

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
  getStaffList.mockResolvedValue({ members: [], notes: [] });
  getStaffJobs.mockResolvedValue({ jobs: [], total: 0, hours: 24, notes: [] });
  getOrgProjects.mockResolvedValue([]);
  getOrgSubjects.mockResolvedValue([]);
  getOrgProject.mockResolvedValue({});
  getOrgSubject.mockResolvedValue({});
  suspendOrganization.mockImplementation(async () => ({
    ...org(), suspended: true, suspend_reason: "жалоба", suspended_by: "s@e.ru",
    suspended_at: "2026-09-10T08:00:00Z", members_list: [],
  }));
  resumeOrganization.mockImplementation(async () => ({ ...org(), members_list: [] }));
  blockUser.mockImplementation(async () => ({}));
  unblockUser.mockImplementation(async () => ({}));
  getPlatformMetrics.mockResolvedValue(metrics());
  downloadMetricsCsv.mockResolvedValue(undefined);
  downloadUsageCsv.mockResolvedValue(undefined);
  assignPlan.mockResolvedValue({ ...org(), members_list: [] });
  getPlans.mockImplementation(async (product: string) => product === "audit"
    ? [{ code: "audit_corp", product: "audit", name: "Корпоративный", price_rub: 0,
         price_on_request: true, max_units: null, unit_name: "дел", max_members: null }]
    : [{ code: "team", product: "business", name: "Команда", price_rub: 2900,
         price_on_request: false, max_units: 50, unit_name: "проектов",
         max_members: 25 }]);
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
  searchStaffUsers.mockResolvedValue([person({
    has_password: false,
    organizations: [{ id: "o1", name: "ООО «Клиент»", role: "analyst", blocked: true,
                      block_reason: "увольнение", last_seen_at: null }],
  })]);
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Пользователи" }));
  expect(await screen.findByText("Коллега")).toBeTruthy();
  expect(screen.getByText("пароль не заводился")).toBeTruthy();
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


// --- F5: два уровня сотрудника и список в интерфейсе ---

const member = (over: Record<string, unknown> = {}) => ({
  id: "s1", email: "operator@e.ru", full_name: "Оператор", role: "operator",
  blocked: false, created_at: "2026-01-10T00:00:00Z",
  last_seen_at: "2026-09-10T08:00:00Z", ...over,
});

it("вкладка «Сотрудники» отвечает, кто ходит к клиентам и на каком уровне", async () => {
  getStaffList.mockResolvedValue({
    members: [member(), member({ id: "s2", email: "support@e.ru", full_name: "Поддержка",
                                 role: "support" })],
    notes: [],
  });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сотрудники" }));

  const table = within(await screen.findByRole("table", { name: "Сотрудники платформы" }));
  expect(table.getByText(/оператор — наблюдение и власть/)).toBeTruthy();
  expect(table.getByText(/поддержка — наблюдение/)).toBeTruthy();
});

it("незаполненная отметка входа — «неизвестно», а не «никогда»", async () => {
  getStaffList.mockResolvedValue({ members: [member({ last_seen_at: null })], notes: [] });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сотрудники" }));
  expect(await screen.findByText("неизвестно")).toBeTruthy();
});

it("сотрудник без уровня назван, а не подписан «поддержкой»", async () => {
  // Подставить сюда значение значило бы ответить на вопрос, на который ответа нет:
  // такому сотруднику власти не даётся, и экран обязан это сказать, а не угадать.
  getStaffList.mockResolvedValue({ members: [member({ role: "" })], notes: [] });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сотрудники" }));
  expect(await screen.findByText(/уровень не назначен — власти нет/)).toBeTruthy();
});

it("оговорки списка сотрудников показываются, а не прячутся", async () => {
  getStaffList.mockResolvedValue({
    members: [member()],
    notes: ["Уровень и признак сотрудника ставятся вне API — scripts/set_staff.py."],
  });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сотрудники" }));
  expect(await screen.findByText(/ставятся вне API/)).toBeTruthy();
});

it("кнопки «повысить» на экране нет — уровень ставится вне интерфейса", async () => {
  getStaffList.mockResolvedValue({ members: [member()], notes: [] });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сотрудники" }));
  await screen.findByRole("table", { name: "Сотрудники платформы" });
  // Правило B1 не ослаблено: маршрут, повышающий права, сам становится главной мишенью.
  expect(screen.queryByRole("button", { name: /уровень|повысить|назначить/i })).toBeNull();
});

it("отбор по сотруднику уходит на сервер, отбор по клиенту сужает показанное", async () => {
  getStaffLog.mockResolvedValue({ entries: [
    { id: "l1", actor_email: "a@e.ru", action: "staff.org_view", organization_id: "o1",
      organization_name: "ООО «Клиент»", details: "", created_at: "2026-09-10T08:00:00Z" },
    { id: "l2", actor_email: "b@e.ru", action: "staff.orgs_list", organization_id: "",
      organization_name: "Другая", details: "", created_at: "2026-09-10T09:00:00Z" },
  ] });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Журнал сотрудников" }));
  await screen.findByText("staff.org_view");

  fireEvent.change(screen.getByLabelText("Отбор по сотруднику"), { target: { value: "a@" } });
  await waitFor(() => expect(getStaffLog).toHaveBeenCalledWith(100, "a@"));

  fireEvent.change(screen.getByLabelText("Отбор по клиенту"), { target: { value: "Другая" } });
  await waitFor(() => expect(screen.queryByText("staff.org_view")).toBeNull());
  expect(screen.getByText("staff.orgs_list")).toBeTruthy();
});

it("пустой отбор в журнале объясняет себя, а не притворяется пустым журналом", async () => {
  getStaffLog.mockResolvedValue({ entries: [
    { id: "l1", actor_email: "a@e.ru", action: "staff.org_view", organization_id: "o1",
      organization_name: "ООО «Клиент»", details: "", created_at: "2026-09-10T08:00:00Z" },
  ] });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Журнал сотрудников" }));
  await screen.findByText("staff.org_view");

  fireEvent.change(screen.getByLabelText("Отбор по клиенту"), { target: { value: "нет такого" } });
  expect(await screen.findByText(/По отбору ничего не найдено/)).toBeTruthy();
  expect(screen.queryByText("Журнал пуст")).toBeNull();
});


// --- B2: власть оператора над клиентом ---

it("приостановка требует причины и обещает клиенту его же данные", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "ООО «Клиент»" }));
  fireEvent.click(await screen.findByRole("button", { name: "Приостановить" }));

  // Кнопка в диалоге неактивна, пока причина не названа: ограничение без причины
  // неотличимо от поломки для того, кому его покажут.
  const dialog = within(screen.getByRole("dialog"));
  expect((dialog.getByRole("button", { name: "Приостановить" }) as HTMLButtonElement)
    .disabled).toBe(true);
  expect(dialog.getByText(/Данные не отбираются/)).toBeTruthy();

  fireEvent.change(dialog.getByLabelText("Причина"), { target: { value: "жалоба" } });
  fireEvent.click(dialog.getByRole("button", { name: "Приостановить" }));
  await waitFor(() => expect(suspendOrganization).toHaveBeenCalledWith("o1", "жалоба"));
  expect(await screen.findByText(/жалоба · s@e.ru/)).toBeTruthy();
});

it("приостановленную организацию видно в списке, не открывая карточку", async () => {
  getStaffOrganizations.mockResolvedValue({
    organizations: [org({ suspended: true } as Partial<StaffOrg>)], total: 1,
  });
  show();
  expect(await screen.findByText("приостановлена")).toBeTruthy();
});

it("блокировка учётной записи названа как «во всех организациях сразу»", async () => {
  searchStaffUsers.mockResolvedValue([person()]);
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Пользователи" }));
  fireEvent.click(await screen.findByRole("button", { name: "Заблокировать" }));

  // Отличие от приостановки участия (A1) сказано прямо: путать их — значит однажды
  // отключить человека у всех клиентов вместо одного.
  const dialog = within(screen.getByRole("dialog"));
  expect(dialog.getByText(/во все организации сразу/)).toBeTruthy();
  fireEvent.change(dialog.getByLabelText("Причина"), { target: { value: "мошенничество" } });
  fireEvent.click(dialog.getByRole("button", { name: "Заблокировать" }));
  await waitFor(() => expect(blockUser).toHaveBeenCalledWith("u9", "мошенничество"));
});

it("сотруднику платформы кнопки блокировки не даёт", async () => {
  searchStaffUsers.mockResolvedValue([
    person({ id: "u2", email: "s2@e.ru", full_name: "Коллега-оператор", is_staff: true }),
  ]);
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Пользователи" }));
  await screen.findByText("Коллега-оператор");
  expect(screen.queryByRole("button", { name: "Заблокировать" })).toBeNull();
});


// --- B3: сводка платформы ---

it("сводка показывает числа вместе с тем, чего они не значат", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  expect((await screen.findAllByText("12")).length).toBeGreaterThan(0);  // организаций
  expect(screen.getByText(/активны за 7 дн.: 5/)).toBeTruthy();
  expect(screen.getByText(/проектов считали \/ выгрузок документов/)).toBeTruthy();
  // Оговорка — на экране, а не в подсказке: без неё ноль читается как «не было».
  expect(screen.getByText(/Журнал ведётся с 01.08.2026/)).toBeTruthy();
});

it("«без отметки» названо отдельно от «неактивны»", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  expect(await screen.findByText(/без отметки: 4/)).toBeTruthy();
});

it("пустой месяц остаётся в ряду роста", async () => {
  // Отбор по таблице роста: месяцы теперь есть и в выручке (F2), и общий поиск по
  // тексту нашёл бы оба ряда сразу.
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  await screen.findByText("Появлялось по месяцам");
  const months = [...document.querySelectorAll(
    '[aria-label="Рост по месяцам"] [role="rowheader"]')].map((n) => n.textContent);
  expect(months).toEqual(["2026-08", "2026-09"]);
});

it("смена окна перезапрашивает сводку тем же периодом", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  await waitFor(() => expect(getPlatformMetrics).toHaveBeenCalledWith(30));
  fireEvent.change(await screen.findByLabelText("Период"), { target: { value: "7" } });
  await waitFor(() => expect(getPlatformMetrics).toHaveBeenCalledWith(7));
});

it("без оформленных подписок разрез тарифов не показывает нулей", async () => {
  getPlatformMetrics.mockResolvedValue(metrics({ plans: [] }));
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  expect(await screen.findByText(/Оформленных подписок нет/)).toBeTruthy();
});


// --- E3: воронка и удержание ---

it("воронка активации говорит «когда-нибудь», а не «за период»", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  expect(await screen.findByText("Завели проект или дело")).toBeTruthy();
  expect(screen.getByText("75%")).toBeTruthy();
  expect(screen.getByText(/когда-нибудь/)).toBeTruthy();
});

it("без событий удержание названо неизмеряемым, а не нарисовано нулём", async () => {
  // «0%» читалось бы как «все ушли» — это другое утверждение.
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  expect(await screen.findByText(/Не измеряется/)).toBeTruthy();
  expect(screen.getByText(/USAGE_EVENTS/)).toBeTruthy();
});

it("когорта без пришедших не выдаётся за когорту с нулевым возвратом", async () => {
  getPlatformMetrics.mockResolvedValue(metrics({
    usage_collected: true,
    retention: [
      { month: "2026-07", arrived: 4, returned: 3 },
      { month: "2026-08", arrived: 0, returned: null },
    ],
  }));
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  expect(await screen.findByText("3 из 4")).toBeTruthy();
  expect(screen.getByText("не измеряется")).toBeTruthy();
});

// --- F8: отток ---

it("отток показан двумя картинами рядом, а не одним числом", async () => {
  // Журнал отвечает «что записано как случившееся», платежи — «кто платил и перестал».
  // Доля считается **внутри** платежей: делить журнал на платежи значило бы свести две
  // картины в одно число, у которого нет смысла.
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  await screen.findByText("Отток");
  const row = [...document.querySelectorAll('[aria-label="Отток по месяцам"] [role="row"]')]
    .find((n) => n.textContent?.startsWith("2026-08"));
  expect(row?.textContent).toContain("3 / 1");
  expect(row?.textContent).toContain("50%");
});

it("определение оттока названо на самом экране", async () => {
  // «Была платная подписка и не стало»: триал, не ставший платным, — воронка, и
  // смешать их значит получить число, которым нельзя пользоваться.
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  expect(await screen.findByText(/воронка, а не отток/)).toBeTruthy();
});

it("непосчитанный месяц говорит «не измеряется», а не показывает ноль", async () => {
  getPlatformMetrics.mockResolvedValue(metrics({
    churn: {
      months: [{ month: "2026-08", expired: null, downgraded: null,
                 payers: 0, stopped: 0, rate: null }],
      expiry_logged: true, unnamed_plan_changes: 0,
    },
  }));
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  // Два прочерка: «не продлили» и «ушли на бесплатный» — оба из одной неизвестности.
  expect((await screen.findAllByText("не измеряется")).length).toBe(2);
});

it("невыполненный скрипт назван причиной, а не спрятан за нулём", async () => {
  // Записи об окончании периода оставляет эксплуатация, а не приложение: пока скрипт
  // не запускали, ноль ушедших означал бы «никто не уходит».
  getPlatformMetrics.mockResolvedValue(metrics({
    churn: { months: [], expiry_logged: false, unnamed_plan_changes: 0 },
  }));
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  expect(await screen.findByText(/не измеряется/)).toBeTruthy();
  expect(screen.getByText(/expire_subscriptions/)).toBeTruthy();
});

it("записи без прежнего тарифа названы, а не молча пропущены", async () => {
  getPlatformMetrics.mockResolvedValue(metrics({
    churn: { months: [], expiry_logged: true, unnamed_plan_changes: 7 },
  }));
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  expect(await screen.findByText(/В 7 записях о смене тарифа прежний тариф не назван/))
    .toBeTruthy();
});

it("события выгружаются отдельно от сводки: это разные вопросы", async () => {
  // Сводка отвечает «сколько клиентов и кто жив», события — «как пользуются». Один
  // файл на оба вопроса означал бы, что в нём есть поведение людей (OPEN-DECISIONS §7).
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  fireEvent.click(await screen.findByRole("button", { name: "События CSV" }));
  await waitFor(() => expect(downloadUsageCsv).toHaveBeenCalled());
  expect(downloadMetricsCsv).not.toHaveBeenCalled();
});

// --- Назначение тарифа (F1) ---

const openPlanModal = async () => {
  show();
  fireEvent.click(await screen.findByText("ООО «Клиент»"));
  fireEvent.click(await screen.findByRole("button", { name: "Назначить тариф" }));
  return screen.findByLabelText("Тариф");
};

it("оператор назначает оплаченный по счёту тариф со сроком", async () => {
  // До F1 тариф не мог выдать никто: клиент выдавал его себе сам и бесплатно, а у
  // платформы двери не было вовсе — «по запросу» оставался непродаваемым.
  const select = await openPlanModal();
  fireEvent.change(select, { target: { value: "team" } });
  fireEvent.change(await screen.findByLabelText("Оплачено месяцев"),
                   { target: { value: "6" } });
  fireEvent.change(screen.getByLabelText("Основание"), { target: { value: "счёт № 42" } });
  fireEvent.click(screen.getByRole("button", { name: "Назначить" }));

  await waitFor(() => expect(assignPlan).toHaveBeenCalledWith("o1", "team", 6, "счёт № 42"));
});

it("тарифу без цены срок не предлагается вовсе", async () => {
  // Отключённое поле выглядит как поломка; срок у такого тарифа был бы выдуманным.
  const select = await openPlanModal();
  fireEvent.change(select, { target: { value: "audit_corp" } });
  expect(await screen.findByText(/Срок не ставится/)).toBeTruthy();
  expect(screen.queryByLabelText("Оплачено месяцев")).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Назначить" }));
  await waitFor(() => expect(assignPlan).toHaveBeenCalledWith("o1", "audit_corp", null, ""));
});

// --- Деньги (F2) ---

it("выручка показана деньгами и названа деньгами месяца, а не периода", async () => {
  // Признание по периодам требует учётной политики, которой у платформы нет: говорить
  // «выручка за март», имея в виду «деньги, пришедшие в марте», можно только назвав это.
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  expect(await screen.findByText("Деньги по месяцам")).toBeTruthy();
  expect(screen.getByText("2 900")).toBeTruthy();
  expect(screen.getByText(/по дате поступления/)).toBeTruthy();
  expect(screen.getByText(/Возвраты платформа не учитывает/)).toBeTruthy();
});

it("пустой месяц выручки остаётся в ряду нулём", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Сводка" }));
  await screen.findByText("Деньги по месяцам");
  const rows = [...document.querySelectorAll('[aria-label="Выручка по месяцам"] [role="row"]')];
  expect(rows.length).toBe(3);   // шапка + два месяца, включая нулевой
});

it("платежи клиента видны в карточке, и неуспешные не прячутся", async () => {
  getStaffOrganization.mockResolvedValue({
    ...org(), members_list: [], payments_total: 2,
    payments: [
      { id: "p1", created_at: "2026-09-01T10:00:00Z", plan_code: "team",
        amount_rub: 2900, status: "succeeded", provider: "yookassa" },
      { id: "p2", created_at: "2026-08-20T10:00:00Z", plan_code: "team",
        amount_rub: 2900, status: "canceled", provider: "yookassa" },
    ],
  } as unknown as StaffOrgDetail);
  show();
  fireEvent.click(await screen.findByText("ООО «Клиент»"));
  expect(await screen.findByText("Платежи")).toBeTruthy();
  // «Карта не прошла» — это разговор с клиентом, а не мусор.
  expect(screen.getByText("отменён")).toBeTruthy();
});

it("оплата по счёту названа проведённой оператором", async () => {
  getStaffOrganization.mockResolvedValue({
    ...org(), members_list: [], payments_total: 1,
    payments: [{ id: "p1", created_at: "2026-09-01T10:00:00Z", plan_code: "team",
                 amount_rub: 5800, status: "succeeded", provider: "manual" }],
  } as unknown as StaffOrgDetail);
  show();
  fireEvent.click(await screen.findByText("ООО «Клиент»"));
  expect(await screen.findByText(/по счёту, провёл оператор/)).toBeTruthy();
});

it("пустые платежи объясняют себя, а не молчат", async () => {
  // Ноль читался бы как «клиент не платил», хотя платформа просто не видит переводов
  // мимо продукта.
  show();
  fireEvent.click(await screen.findByText("ООО «Клиент»"));
  expect(await screen.findByText(/прямые переводы мимо продукта/)).toBeTruthy();
});


// --- F4: содержимое моделей — только по гранту клиента ---

const NO_GRANT = "Клиент не открывал доступ к своим моделям. Содержимое проектов и дел "
  + "платформе не видно: доступ выдаёт сама организация.";

function withAccess(access: Record<string, unknown>) {
  getStaffOrganization.mockResolvedValue({
    ...org(), members_list: [], access,
  } as unknown as StaffOrgDetail);
}

async function openCard() {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "ООО «Клиент»" }));
  await screen.findByText(/Ваш визит записан в журнал этой организации/i);
}

it("без гранта содержимого нет, и экран называет причину", async () => {
  withAccess({ granted: false, reason: NO_GRANT });
  await openCard();

  expect(await screen.findByText(new RegExp("доступ выдаёт сама организация", "i")))
    .toBeTruthy();
  // Не запрошено — граница держится запросами, а не тем, что мы ничего не нарисовали.
  expect(getOrgProjects).not.toHaveBeenCalled();
  expect(getOrgSubjects).not.toHaveBeenCalled();
});

it("по гранту показываются модели — и на каком основании", async () => {
  withAccess({ granted: true, expires_at: "2026-09-22T18:00:00Z",
               granted_by_email: "owner@e.ru", grant_reason: "не считается проект" });
  getOrgProjects.mockResolvedValue([
    { id: "p1", name: "Покупка завода в Твери", updated_at: "2026-09-19T10:00:00Z" }]);
  await openCard();

  expect(await screen.findByText(/Клиент открыл доступ до/)).toBeTruthy();
  expect(screen.getByText(/не считается проект/)).toBeTruthy();
  expect(await screen.findByText("Покупка завода в Твери")).toBeTruthy();
});

it("оператор предупреждён, что открытие попадёт в журнал клиента", async () => {
  // До нажатия, а не после: приход постороннего клиент увидит построчно, и тот, кто
  // приходит, обязан это знать.
  withAccess({ granted: true, expires_at: "2026-09-22T18:00:00Z",
               granted_by_email: "owner@e.ru", grant_reason: "разбор" });
  await openCard();

  expect(await screen.findByText(/попадает в журнал этой организации отдельной строкой/))
    .toBeTruthy();
});

it("модель открывается явным действием и несёт строку об основании", async () => {
  withAccess({ granted: true, expires_at: "2026-09-22T18:00:00Z",
               granted_by_email: "owner@e.ru", grant_reason: "разбор" });
  getOrgProjects.mockResolvedValue([
    { id: "p1", name: "Покупка завода в Твери", updated_at: "2026-09-19T10:00:00Z" }]);
  getOrgProject.mockResolvedValue({
    id: "p1", name: "Покупка завода в Твери", updated_at: "2026-09-19T10:00:00Z",
    model: { header: { name: "Покупка завода в Твери" } },
    note: "Содержимое модели клиента. Доступ открыт самой организацией (owner@e.ru).",
  });
  await openCard();

  // Список сам по себе модель не запрашивает: открытие — отдельное действие, и оно
  // отдельная строка в журнале клиента.
  await screen.findByText("Покупка завода в Твери");
  expect(getOrgProject).not.toHaveBeenCalled();

  fireEvent.click(screen.getAllByRole("button", { name: "Открыть" })[0]);
  await waitFor(() => expect(getOrgProject).toHaveBeenCalledWith("o1", "p1"));
  expect(await screen.findByText(/Доступ открыт самой организацией/)).toBeTruthy();
});

it("выдать себе доступ оператору нечем — кнопки нет", async () => {
  // Правило 6 не отменено: у него появился ключ, и ключ у клиента.
  withAccess({ granted: false, reason: NO_GRANT });
  await openCard();
  await screen.findByText(/доступ выдаёт сама организация/i);

  expect(screen.queryByRole("button", { name: /открыть доступ|запросить доступ/i }))
    .toBeNull();
});


// --- F3: видно, что зависло ---

const job = (over: Record<string, unknown> = {}) => ({
  id: "j1", organization_id: "o1", organization_name: "ООО «Клиент»",
  project_id: "p1", kind: "monte_carlo", created_at: "2026-09-20T08:00:00Z",
  age_minutes: 40, status: "pending", note: "", ...over,
});

async function openJobs() {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Эксплуатация" }));
}

it("зависшая задача видна вместе со своим возрастом", async () => {
  // «В очереди сорок минут» — это и есть сигнал: без возраста список ничего не говорит.
  getStaffJobs.mockResolvedValue({ jobs: [job()], total: 1, hours: 24, notes: [] });
  await openJobs();

  const table = within(await screen.findByRole("table", { name: "Фоновые задачи" }));
  expect(table.getByText("ООО «Клиент»")).toBeTruthy();
  expect(table.getByText("40 минут")).toBeTruthy();
  expect(table.getByText("в очереди")).toBeTruthy();
});

it("«неизвестно» показано как «неизвестно», а не как «упало»", async () => {
  getStaffJobs.mockResolvedValue({
    jobs: [job({ status: "unknown",
                 note: "Состояние неизвестно: хранилище результатов не ответило." })],
    total: 1, hours: 24, notes: [] });
  await openJobs();

  expect(await screen.findByText("неизвестно")).toBeTruthy();
  expect(screen.queryByText("упала")).toBeNull();
  // Причина едет рядом с самим «неизвестно»: без неё оно неотличимо от поломки.
  expect(screen.getByText(/хранилище результатов не ответило/)).toBeTruthy();
});

it("пустой список объясняет свою пустоту, а не выглядит поломкой", async () => {
  await openJobs();
  expect(await screen.findByText("Задач за это окно не было")).toBeTruthy();
  expect(screen.getByText(/Это не поломка/)).toBeTruthy();
});

it("окно переключается, и запрос уходит с ним", async () => {
  await openJobs();
  await waitFor(() => expect(getStaffJobs).toHaveBeenCalledWith(24));
  fireEvent.click(screen.getByRole("button", { name: "Неделя" }));
  await waitFor(() => expect(getStaffJobs).toHaveBeenCalledWith(24 * 7));
});

it("оговорки списка задач показаны", async () => {
  getStaffJobs.mockResolvedValue({
    jobs: [job()], total: 1, hours: 24,
    notes: ["Результатов задач здесь нет: числа Монте-Карло — содержимое модели клиента.",
            "Список задач растёт и не чистится: строки не удаляются никогда."] });
  await openJobs();

  expect(await screen.findByText(/содержимое модели клиента/)).toBeTruthy();
  expect(screen.getByText(/не чистится/)).toBeTruthy();
});
