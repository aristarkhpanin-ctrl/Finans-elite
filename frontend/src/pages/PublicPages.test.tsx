// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LegalDoc } from "../api/legal";
import type { Plan } from "../api/org";

/**
 * Публичные страницы (L5): главная, тарифы, документы. Числа и тексты — с сервера: цена на
 * сайте и в оплате одна, обещание про бесплатный тариф — из каталога, черновик документа
 * виден **над** текстом, незаданный реквизит назван.
 */

vi.mock("../components/CubeHero", () => ({ CubeHero: () => null }));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ loginDemo: vi.fn() }) }));
const getCapabilities = vi.fn();
vi.mock("../api/auth", () => ({ getCapabilities: () => getCapabilities() }));
const getPlans = vi.fn();
vi.mock("../api/org", () => ({ getPlans: (p?: string) => getPlans(p) }));
const getLegalDoc = vi.fn();
const getLegalIndex = vi.fn();
vi.mock("../api/legal", async (orig) => ({
  ...(await orig<typeof import("../api/legal")>()),
  getLegalDoc: (slug: string) => getLegalDoc(slug),
  getLegalIndex: () => getLegalIndex(),
}));
const getToken = vi.fn();
vi.mock("../api/client", async (orig) => ({
  ...(await orig<typeof import("../api/client")>()),
  getToken: () => getToken(),
}));

const { HomePage } = await import("./HomePage");
const { PricingPage } = await import("./PricingPage");
const { LegalPage } = await import("./LegalPage");

const PLANS: Plan[] = [
  { code: "free", product: "business", name: "Бесплатный", price_rub: 0, price_on_request: false,
    max_units: 5, unit_name: "проектов", max_members: 5, annual_price_rub: null,
    annual_free_months: 0 },
  { code: "team", product: "business", name: "Команда", price_rub: 2900, price_on_request: false,
    max_units: 50, unit_name: "проектов", max_members: 25, annual_price_rub: 29000,
    annual_free_months: 2 },
  { code: "audit_corp", product: "audit", name: "Корпоративный", price_rub: 0,
    price_on_request: true, max_units: null, unit_name: "дел", max_members: null,
    annual_price_rub: null, annual_free_months: 0 },
];

function show(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/projects" element={<div>Рабочая область</div>} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/legal" element={<LegalPage />} />
          <Route path="/legal/:doc" element={<LegalPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getToken.mockReturnValue(null);
  getCapabilities.mockResolvedValue({ mail: false, error_tracking: false, demo: false });
  getPlans.mockImplementation((p?: string) =>
    Promise.resolve(p ? PLANS.filter((x) => x.product === p) : PLANS));
});

describe("главная", () => {
  it("гостю — что за сервисы; обещание про бесплатный тариф — из каталога", async () => {
    show("/");
    expect(screen.getByRole("heading", { level: 1 })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Финанс-Элит" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Финанс-Аудит" })).toBeTruthy();
    expect(await screen.findByText(/Тариф «Бесплатный» бесплатный и без срока: до 5 проектов/))
      .toBeTruthy();
    // Документы — в подвале каждой публичной страницы.
    for (const name of ["Оферта", "Политика обработки ПД", "Согласие на обработку ПД", "Реквизиты"]) {
      expect(screen.getByRole("link", { name })).toBeTruthy();
    }
  });

  it("вошедшего сразу ведёт в работу", () => {
    getToken.mockReturnValue("token");
    show("/");
    expect(screen.getByText("Рабочая область")).toBeTruthy();
  });

  it("кнопки демо нет там, где демо не заведено", async () => {
    show("/");
    await waitFor(() => expect(getCapabilities).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /Посмотреть демо/ })).toBeNull();
  });
});

describe("тарифы", () => {
  it("цены из каталога: «по запросу» — не ноль, год — с подарком", async () => {
    show("/pricing");
    expect(await screen.findByText("Команда")).toBeTruthy();
    expect(screen.getByText(/Год — 29\s000 ₽ \(2 месяца в подарок\)/)).toBeTruthy();
    expect(screen.getByText("По запросу")).toBeTruthy();
    expect(screen.getByText("Бесплатно")).toBeTruthy();
    expect(screen.getByText(/дел без ограничения · участников без ограничения/)).toBeTruthy();
  });
});

const DRAFT_DOC: LegalDoc = {
  slug: "offer", title: "Оферта", summary: "Условия", edition: "черновик", draft: true,
  draft_note: "Черновик: текст подготовлен платформой и юристом не проверен.",
  sections: [{ heading: "1. Общие положения", paragraphs: ["Исполнитель [не указано: ОГРН (ОГРНИП)]."] }],
  missing: ["ОГРН (ОГРНИП)", "адрес"],
};

describe("документы", () => {
  it("черновик и пробелы реквизитов видны над текстом", async () => {
    getLegalDoc.mockResolvedValue(DRAFT_DOC);
    show("/legal/offer");
    expect(await screen.findByRole("heading", { level: 1, name: "Оферта" })).toBeTruthy();
    const text = document.body.textContent ?? "";
    expect(text).toContain("Редакция: черновик");
    expect(text).toContain("В тексте не указано: ОГРН (ОГРНИП), адрес.");
    expect(text.indexOf("юристом не проверен")).toBeLessThan(text.indexOf("1. Общие положения"));
    expect(getLegalDoc).toHaveBeenCalledWith("offer");
  });

  it("утверждённая редакция называет дату и не пугает черновиком", async () => {
    getLegalDoc.mockResolvedValue({ ...DRAFT_DOC, draft: false, draft_note: "",
                                    edition: "2026-10-15", missing: [] });
    show("/legal/offer");
    expect(await screen.findByText("Редакция от 2026-10-15")).toBeTruthy();
    expect(document.body.textContent).not.toContain("черновик");
  });

  it("неизвестный документ — «такого нет» и дорога ко всем", async () => {
    getLegalDoc.mockRejectedValue({ isAxiosError: true, response: { status: 404, data: {} } });
    show("/legal/nope");
    expect((await screen.findByRole("alert")).textContent).toContain("Такого документа нет");
    expect(screen.getByRole("link", { name: "Все документы" }).getAttribute("href")).toBe("/legal");
  });

  it("список документов — с сервера", async () => {
    getLegalIndex.mockResolvedValue({
      edition: "черновик", draft: true, draft_note: "Черновик.",
      documents: [{ slug: "privacy", title: "Политика обработки персональных данных",
                    summary: "Какие данные" }],
    });
    show("/legal");
    expect((await screen.findByRole("link", { name: "Политика обработки персональных данных" }))
      .getAttribute("href")).toBe("/legal/privacy");
  });
});
