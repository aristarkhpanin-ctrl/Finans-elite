// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OrganizationPage } from "./OrganizationPage";

/**
 * Прямой переход на вкладку (пакет G, G4). Письма о деньгах ведут на
 * ``/organization?tab=billing``: пришедший оплатить не должен искать нужную вкладку, а
 * ссылка на «Обзор» заставила бы. Неизвестная вкладка в адресе — не ошибка, а обзор.
 */

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    currentOrgId: "o1",
    organizations: [{ id: "o1", name: "Орг", role: "owner" }],
    user: { email: "owner@e.ru" },
  }),
}));

// Вкладки подменены заглушками: проверяется выбор вкладки, а не их содержимое.
vi.mock("./org/BillingTab", () => ({ BillingTab: () => <div>вкладка оплаты</div> }));
vi.mock("./org/OverviewTab", () => ({ OverviewTab: () => <div>вкладка обзора</div> }));
vi.mock("./org/AuditLogTab", () => ({ AuditLogTab: () => null }));
vi.mock("./org/ProfileTab", () => ({ ProfileTab: () => null }));
vi.mock("./org/MembersTab", () => ({ MembersTab: () => null }));
vi.mock("./org/ActivityTab", () => ({ ActivityTab: () => null }));
vi.mock("./org/BenchmarksTab", () => ({ BenchmarksTab: () => null }));
vi.mock("./org/ChecklistsTab", () => ({ ChecklistsTab: () => null }));
vi.mock("./org/ApiKeysTab", () => ({ ApiKeysTab: () => null }));
vi.mock("./org/SupportAccessTab", () => ({ SupportAccessTab: () => null }));
vi.mock("./org/DataTab", () => ({ DataTab: () => null }));

afterEach(cleanup);

function open(url: string) {
  render(<MemoryRouter initialEntries={[url]}><OrganizationPage /></MemoryRouter>);
}

describe("вкладка из адреса", () => {
  it("?tab=billing открывает оплату сразу", () => {
    open("/organization?tab=billing");
    expect(screen.getByText("вкладка оплаты")).toBeTruthy();
  });

  it("без параметра — обзор, как раньше", () => {
    open("/organization");
    expect(screen.getByText("вкладка обзора")).toBeTruthy();
  });

  it("неизвестная вкладка — обзор, а не пустой экран", () => {
    open("/organization?tab=нет-такой");
    expect(screen.getByText("вкладка обзора")).toBeTruthy();
  });
});
