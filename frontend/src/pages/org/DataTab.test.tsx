// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { OrgDeletionPlan } from "../../api/org";
import { DataTab } from "./DataTab";

/**
 * Забрать всё и уйти (F6).
 *
 * Проверяется то, ради чего экран и сделан: числа видны **до** нажатия, список того, что
 * переживёт удаление, показывается (а не прячется как «мелкий шрифт»), удаление требует
 * пароля и объявляет себя необратимым, а закрыть компанию предлагают только владельцу.
 */

const downloadOrgExport = vi.fn();
const getOrgDeletePreview = vi.fn();
const deleteOrganization = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  downloadOrgExport: (...a: unknown[]) => downloadOrgExport(...a),
  getOrgDeletePreview: (...a: unknown[]) => getOrgDeletePreview(...a),
  deleteOrganization: (...a: unknown[]) => deleteOrganization(...a),
}));

const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));

const refresh = vi.fn();
vi.mock("../../auth/AuthContext", () => ({ useAuth: () => ({ refresh }) }));

const KEPT = [
  "Учётные записи участников: они принадлежат людям, а не организации. "
  + "У 2 из них это единственная организация — после удаления они войдут в пустой продукт.",
  "Записи служебного журнала платформы о визитах её сотрудников к вам.",
  "Оплаченный, но не использованный период при удалении не возвращается.",
];

const plan = (over: Partial<OrgDeletionPlan> = {}): OrgDeletionPlan => ({
  name: "ООО «Клиент»", allowed: true, projects: 4, cases: 2, groups: 0, members: 3,
  members_left_homeless: 2, comments: 7, log_entries: 42, api_keys: 1,
  kept: KEPT, blockers: [], ...over,
} as OrgDeletionPlan);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getOrgDeletePreview.mockResolvedValue(plan());
  downloadOrgExport.mockResolvedValue(undefined);
  deleteOrganization.mockResolvedValue(plan());
});

function show(isOwner = true) {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <DataTab orgId="o1" orgName="ООО «Клиент»" isOwner={isOwner} />
    </QueryClientProvider>,
  );
}

it("выгрузка называет, что внутри и чего внутри нет", async () => {
  show();
  expect(await screen.findByText(/моделями целиком/)).toBeTruthy();
  expect(screen.getByText(/Результатов расчётов внутри нет/)).toBeTruthy();
  expect(screen.getByText(/Файлов внутри нет/)).toBeTruthy();
});

it("выгрузка скачивается одним действием", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Выгрузить всё в JSON" }));
  await waitFor(() => expect(downloadOrgExport)
    .toHaveBeenCalledWith("o1", "ООО «Клиент»"));
});

it("числа исчезающего видны до нажатия", async () => {
  show();
  expect(await screen.findByText(/4 проекта/)).toBeTruthy();
  expect(screen.getByText(/2 дела/)).toBeTruthy();
  expect(screen.getByText(/42 записи журнала/)).toBeTruthy();
});

it("список переживающего удаление показан, а не спрятан", async () => {
  // «Удалим всё» без списка исключений — неправда.
  show();
  expect(await screen.findByText(/Учётные записи участников/)).toBeTruthy();
  expect(screen.getByText(/не возвращается/)).toBeTruthy();
  expect(screen.getByText(/войдут в пустой продукт/)).toBeTruthy();
});

it("удаление требует пароля и объявляет себя необратимым", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Удалить организацию" }));

  const dialog = within(screen.getByRole("dialog"));
  expect(dialog.getByText(/нельзя отменить/)).toBeTruthy();
  expect((dialog.getByRole("button", { name: "Удалить навсегда" }) as HTMLButtonElement)
    .disabled).toBe(true);

  fireEvent.change(dialog.getByLabelText("Ваш пароль"), { target: { value: "secret123" } });
  fireEvent.click(dialog.getByRole("button", { name: "Удалить навсегда" }));
  await waitFor(() => expect(deleteOrganization).toHaveBeenCalledWith("o1", "secret123"));
});

it("после удаления список организаций перечитывается", async () => {
  // Иначе продукт продолжил бы показывать арендатора, которого больше нет, и следующий
  // запрос упёрся бы в отказ без объяснения.
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Удалить организацию" }));
  const dialog = within(screen.getByRole("dialog"));
  fireEvent.change(dialog.getByLabelText("Ваш пароль"), { target: { value: "secret123" } });
  fireEvent.click(dialog.getByRole("button", { name: "Удалить навсегда" }));

  await waitFor(() => expect(refresh).toHaveBeenCalled());
});

it("не-владельцу удаление не предлагается, и отказ назван", async () => {
  show(false);
  expect(await screen.findByText(/только её владелец/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Удалить организацию" })).toBeNull();
  // Выгрузка при этом доступна: забрать данные — не то же самое, что закрыть компанию.
  expect(screen.getByRole("button", { name: "Выгрузить всё в JSON" })).toBeTruthy();
  expect(getOrgDeletePreview).not.toHaveBeenCalled();
});
