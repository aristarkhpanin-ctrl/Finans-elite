// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CalcResponse } from "../api/calc";
import type { SharedPlan } from "../api/share";

/**
 * План по ссылке (L4): посетитель без входа видит, **что** он смотрит — копию, для кого,
 * до какого числа, — раньше чисел; отказ сервера называет свою причину.
 */

const toast = vi.fn();
vi.mock("../components/Toast", () => ({ useToast: () => toast }));
// Куб-марка рисует сцену на matchMedia и requestAnimationFrame — к содержанию страницы
// она отношения не имеет, как и графики со сводкой (у них свои тесты).
vi.mock("../components/CubeHero", () => ({ CubeHero: () => null }));
vi.mock("../components/SummaryView", () => ({ SummaryView: () => null }));
vi.mock("../components/ResultCharts", () => ({ ResultCharts: () => null }));

const getSharedPlan = vi.fn();
vi.mock("../api/share", async (orig) => ({
  ...(await orig<typeof import("../api/share")>()),
  getSharedPlan: (token: string) => getSharedPlan(token),
}));
const downloadSharedBusinessPlan = vi.fn();
vi.mock("../export", () => ({
  downloadSharedBusinessPlan: (token: string, name: string) => downloadSharedBusinessPlan(token, name),
}));

const { SharedPlanPage } = await import("./SharedPlanPage");

const result = {
  n: 12, engine_version: "0.9.58", warnings: [], details: [],
  metrics: { npv: "1500000", irr_annual: "0.31", mirr_annual: null, pi: "1.4", arr: null,
             pb_months: 20, dpb_months: 26, peak_financing_need: "900000",
             pv_investments: "800000", no_return_metrics_note: null },
  valuation: { net_assets: "1", gordon_value: null, dividend_value: null,
               earnings_multiple_value: null, liquidation_value: null },
  product_margins: { products: [], unallocated_direct: "0" },
  division_margins: [], subscription_base: [], participants: [], debt_service: null,
  working_capital_release: null, metrics_foreign: null,
} as unknown as CalcResponse;

const shared: SharedPlan = {
  project_name: "Кофейня у вокзала", version_label: "Отправлено: Сбербанк (04.10.2026)",
  shared_for: "Сбербанк, кредитный комитет", organization: "ООО «Ромашка»",
  created_at: "2026-10-04T10:00:00Z", expires_at: "2026-11-03T10:00:00Z",
  engine_then: "0.9.58", engine_now: "0.9.58", discount_rate_annual: "0.2",
  foreign_code: "", discount_rate_annual_foreign: "0",
  notes: ["Это копия плана на момент отправки: правка проекта после отправки её не меняет."],
  result,
};

function show() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/s/fs_secret"]}>
        <Routes>
          <Route path="/s/:token" element={<SharedPlanPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("план по ссылке", () => {
  it("называет, что это за копия, — до чисел", async () => {
    getSharedPlan.mockResolvedValue(shared);
    show();
    expect(await screen.findByRole("heading", { level: 1, name: "Кофейня у вокзала" })).toBeTruthy();
    expect(getSharedPlan).toHaveBeenCalledWith("fs_secret");
    const text = document.body.textContent ?? "";
    expect(text).toContain("Копия для: Сбербанк, кредитный комитет");
    expect(text).toContain("версия «Отправлено: Сбербанк (04.10.2026)»");
    expect(text).toContain("Это копия плана на момент отправки");
    // Оговорки стоят над показателями, а не под ними.
    expect(text.indexOf("Это копия плана")).toBeLessThan(text.indexOf("Показатели эффективности"));
    expect(document.title).toContain("Кофейня у вокзала");
  });

  it("логотип отправителя — над названием плана, без логотипа — ничего лишнего", async () => {
    getSharedPlan.mockResolvedValue({ ...shared, organization_logo: "data:image/png;base64,AAAA" });
    show();
    expect(await screen.findByRole("img", { name: "Логотип «ООО «Ромашка»»" })).toBeTruthy();
    cleanup();
    getSharedPlan.mockResolvedValue(shared);
    show();
    await screen.findByRole("heading", { level: 1, name: "Кофейня у вокзала" });
    expect(screen.queryByRole("img", { name: /Логотип/ })).toBeNull();
  });

  it("бизнес-план скачивается по той же ссылке", async () => {
    getSharedPlan.mockResolvedValue(shared);
    downloadSharedBusinessPlan.mockResolvedValue(undefined);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Бизнес-план (DOCX)" }));
    await waitFor(() => expect(downloadSharedBusinessPlan)
      .toHaveBeenCalledWith("fs_secret", "Кофейня у вокзала.docx"));
  });

  it("закрытая ссылка говорит причину словами сервера и не предлагает повторить", async () => {
    getSharedPlan.mockRejectedValue({
      isAxiosError: true,
      response: { status: 410, data: { detail: "Ссылку закрыл отправитель 06.10.2026." } },
    });
    show();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Ссылка больше не действует");
    expect(alert.textContent).toContain("Ссылку закрыл отправитель 06.10.2026.");
    expect(screen.queryByRole("button", { name: "Повторить" })).toBeNull();
  });

  it("сбой сети — повторить можно", async () => {
    getSharedPlan.mockRejectedValue(new Error("network"));
    show();
    expect((await screen.findByRole("alert")).textContent).toContain("План не открылся");
    expect(screen.getByRole("button", { name: "Повторить" })).toBeTruthy();
  });
});
