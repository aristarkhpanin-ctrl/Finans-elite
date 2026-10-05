// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TemplateInfo } from "../api/projects";
import { nextMonthStart, ProjectOnboardingPage, splitByGoal } from "./ProjectOnboardingPage";

/**
 * Мастер первого проекта (G12). Проверяются решения, которые легко потерять при
 * следующей правке экрана: проект создаётся одним запросом на последнем шаге, оговорка
 * шаблона видна **до** создания, горизонт шаблона не меняется (движок дополнил бы ряды
 * нулями), а «действующий бизнес» ведёт к шаблонам с остатками на старте и к
 * стартовому балансу.
 */

const createProject = vi.fn();
const createProjectFromTemplate = vi.fn();
const createProjectFromModel = vi.fn();
const listTemplates = vi.fn();
vi.mock("../api/projects", async (orig) => ({
  ...(await orig<typeof import("../api/projects")>()),
  createProject: (...a: unknown[]) => createProject(...a),
  createProjectFromTemplate: (...a: unknown[]) => createProjectFromTemplate(...a),
  createProjectFromModel: (...a: unknown[]) => createProjectFromModel(...a),
  listTemplates: () => listTemplates(),
}));

const listAuditSubjects = vi.fn();
const getBusinessPlanDraft = vi.fn();
vi.mock("../api/audit", async (orig) => ({
  ...(await orig<typeof import("../api/audit")>()),
  listAuditSubjects: () => listAuditSubjects(),
  getBusinessPlanDraft: (...a: unknown[]) => getBusinessPlanDraft(...a),
}));

// Куб-марка — анимированная сцена на RAF; в тесте она не нужна и только шумит.
vi.mock("../components/CubeHero", () => ({ CubeHero: () => <div data-testid="cube" /> }));

const DISCLAIMER = "Числа выдуманы автором шаблона: это не отраслевая норма.";

const TEMPLATES: TemplateInfo[] = [
  { id: "cafe", name: "Кофейня", industry: "Общепит", description: "Точка с рецептурой.",
    shows: "Рецептура и штат.", assumptions: [DISCLAIMER, "Аренда 150 тыс."],
    duration_months: 24, existing_business: false },
  { id: "retail", name: "Магазин у дома", industry: "Розница",
    description: "Действующая точка.", shows: "", assumptions: [DISCLAIMER],
    duration_months: 24, existing_business: true },
];

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  listTemplates.mockResolvedValue(TEMPLATES);
  createProject.mockResolvedValue({ id: "p1", name: "Новый проект" });
  createProjectFromTemplate.mockResolvedValue({ id: "p2", name: "Кофейня" });
  createProjectFromModel.mockResolvedValue({ id: "p3", name: "ООО «Цель» — бизнес-план" });
  listAuditSubjects.mockResolvedValue([
    { id: "s1", name: "ООО «Цель»", industry: "Перевозки", balanced: true, n_periods: 3,
      created_at: "", updated_at: "", light: null },
    { id: "s2", name: "ООО «Кривой баланс»", industry: "", balanced: false, n_periods: 1,
      created_at: "", updated_at: "", light: null },
  ]);
  getBusinessPlanDraft.mockResolvedValue({
    model: { header: { name: "ООО «Цель»", start_date: "2026-01-01", duration_months: 36 },
             company: { starting_balance: { cash: "300000" } } },
    notes: ["Краткосрочные обязательства → краткосрочные займы (B22): форма дела не делит их."],
    period_label: "2025", start_date: "2026-01-01", revaluations: [],
  });
});

function show() {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <MemoryRouter initialEntries={["/projects/onboarding"]}>
        <Routes>
          <Route path="/projects/onboarding" element={<ProjectOnboardingPage />} />
          <Route path="/projects" element={<div>Список проектов</div>} />
          <Route path="/projects/:id" element={<div>Редактор проекта</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const click = (name: RegExp | string) =>
  fireEvent.click(screen.getByRole("button", { name }));
const fill = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe("Дата старта по умолчанию", () => {
  it("первое число следующего месяца, без часового пояса", () => {
    expect(nextMonthStart(new Date(2026, 8, 26))).toBe("2026-10-01");
    expect(nextMonthStart(new Date(2026, 11, 31, 23, 30))).toBe("2027-01-01");
  });
});

describe("Шаблоны под цель", () => {
  it("действующий бизнес — шаблоны с остатками на старте первыми", () => {
    const [fits, others] = splitByGoal(TEMPLATES, "existing");
    expect(fits.map((t) => t.id)).toEqual(["retail"]);
    expect(others.map((t) => t.id)).toEqual(["cafe"]);
  });
});

describe("Мастер", () => {
  it("шаблон: оговорка до создания, горизонт не меняется, проект — одним запросом", async () => {
    show();
    click("Дальше");                                             // цель: новый бизнес
    fireEvent.click(await screen.findByRole("button", { name: /Кофейня/ }));
    // Оговорка — на шаге выбора, до создания проекта.
    expect(await screen.findByText(DISCLAIMER)).toBeTruthy();
    expect(screen.getByText(/Горизонт шаблона — 24 месяца/)).toBeTruthy();
    expect(screen.queryByLabelText("Горизонт, месяцев")).toBeNull();
    fill("Дата старта", "2027-03-01");
    click("Дальше");
    await screen.findByLabelText("Название проекта");
    // Мутация зовётся через микрозадачи: даём им пройти, иначе проверка была бы слепой.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(createProjectFromTemplate).not.toHaveBeenCalled();    // до последней кнопки — ничего
    fill("Название проекта", "Кофейня на Лесной");
    click("Создать проект");
    expect(await screen.findByText(/Числа шаблона выдуманы/)).toBeTruthy();
    expect(createProjectFromTemplate).toHaveBeenCalledTimes(1);
    expect(createProjectFromTemplate).toHaveBeenCalledWith("cafe", "Кофейня на Лесной",
                                                           "2027-03-01");
    expect(createProject).not.toHaveBeenCalled();
    click("Открыть редактор");
    expect(screen.getByText("Редактор проекта")).toBeTruthy();
  });

  it("пустая модель: горизонт выбирается и проверяется", async () => {
    show();
    click("Дальше");
    await screen.findByRole("button", { name: /Кофейня/ });      // шаблоны загрузились
    fill("Горизонт, месяцев", "0");
    expect(screen.getByText("Целое число от 1 до 600")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Дальше" }) as HTMLButtonElement).disabled)
      .toBe(true);
    fill("Горизонт, месяцев", "48");
    fill("Дата старта", "2027-01-01");
    click("Дальше");
    click("Создать проект");
    await waitFor(() => expect(createProject).toHaveBeenCalledWith("Новый проект", 48,
                                                                   "2027-01-01"));
  });

  it("действующий бизнес: подходящий шаблон первым и стартовый баланс в «что дальше»",
     async () => {
    show();
    fireEvent.click(screen.getByRole("radio", { name: /Действующий бизнес/ }));
    click("Дальше");
    const heads = await screen.findAllByText(/Шаблоны под цель|Другие шаблоны/);
    expect(heads.map((h) => h.textContent)).toEqual(["Шаблоны под цель", "Другие шаблоны"]);
    const order = screen.getAllByRole("button").map((b) => b.textContent ?? "");
    expect(order.findIndex((t) => t.includes("Магазин у дома")))
      .toBeLessThan(order.findIndex((t) => t.includes("Кофейня")));
    click("Дальше");                                             // пустая модель
    click("Создать проект");
    expect(await screen.findByText(/остатки на дату старта/)).toBeTruthy();
  });

  it("список шаблонов не загрузился — это сказано, пустая модель доступна", async () => {
    listTemplates.mockRejectedValue(new Error("сеть"));
    show();
    click("Дальше");
    expect(await screen.findByText(/Список шаблонов не загрузился/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Пустая модель/ })).toBeTruthy();
  });

});

describe("Из дела «Аудита» (G14)", () => {
  const toAuditStep = async () => {
    show();
    fireEvent.click(screen.getByRole("radio", { name: /Из дела «Аудита»/ }));
    click("Дальше");
    return screen.findByRole("button", { name: /ООО «Цель»/ });
  };

  it("единицу сумм называет человек: без неё черновик не запрашивается", async () => {
    fireEvent.click(await toAuditStep());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(getBusinessPlanDraft).not.toHaveBeenCalled();
    expect(screen.getByText(/Единицы у дела нет/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Дальше" }) as HTMLButtonElement).disabled)
      .toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: /В тысячах рублей/ }));
    await waitFor(() => expect(getBusinessPlanDraft).toHaveBeenCalledWith("s1", 1000, 36));
  });

  it("оговорки черновика — до создания; проект — одним запросом из черновика", async () => {
    fireEvent.click(await toAuditStep());
    fireEvent.click(screen.getByRole("radio", { name: /В рублях/ }));
    expect(await screen.findByText(/краткосрочные займы \(B22\)/)).toBeTruthy();
    expect((screen.getByLabelText("Дата старта") as HTMLInputElement).value)
      .toBe("2026-01-01");                                     // дата — после периода дела
    fill("Горизонт, месяцев", "24");
    click("Дальше");
    await screen.findByLabelText("Название проекта");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(createProjectFromModel).not.toHaveBeenCalled();
    click("Создать проект");
    expect(await screen.findByText(/Происхождение модели/)).toBeTruthy();
    expect(createProjectFromModel).toHaveBeenCalledTimes(1);
    const [title, model] = createProjectFromModel.mock.calls[0];
    expect(title).toBe("ООО «Цель» — бизнес-план");
    expect(model.header).toMatchObject({ start_date: "2026-01-01", duration_months: 24 });
    expect(model.company.starting_balance.cash).toBe("300000");
  });

  it("своя дата старта не затирается черновиком", async () => {
    fireEvent.click(await toAuditStep());
    fireEvent.click(screen.getByRole("radio", { name: /В рублях/ }));
    await screen.findByText(/краткосрочные займы/);
    fill("Дата старта", "2026-04-01");
    expect((screen.getByLabelText("Дата старта") as HTMLInputElement).value).toBe("2026-04-01");
  });

  it("отказ сервера назван его словами, дальше не пройти", async () => {
    getBusinessPlanDraft.mockRejectedValue(Object.assign(new Error("422"), {
      isAxiosError: true,
      response: { status: 422, data: { detail: "актив не равен пассиву, разница 100,00" } },
    }));
    fireEvent.click(await toAuditStep());
    expect(screen.getByText(/баланс не сходится — перенести его нельзя/)).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: /В рублях/ }));
    expect(await screen.findByText(/разница 100,00/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Дальше" }) as HTMLButtonElement).disabled)
      .toBe(true);
  });

  it("со страницы дела мастер открывается с выбранным делом", async () => {
    render(
      <QueryClientProvider client={new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })}>
        <MemoryRouter initialEntries={["/projects/onboarding?from=audit&subject=s1"]}>
          <Routes>
            <Route path="/projects/onboarding" element={<ProjectOnboardingPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const picked = await screen.findByRole("button", { name: /ООО «Цель»/ });
    expect(picked.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText(/Единицы у дела нет/)).toBeTruthy();       // единицы — всё равно спрашиваются
  });

  it("нет доступа к «Аудиту» — сказано, а не пусто", async () => {
    listAuditSubjects.mockRejectedValue(Object.assign(new Error("403"), {
      isAxiosError: true, response: { status: 403, data: {} } }));
    show();
    fireEvent.click(screen.getByRole("radio", { name: /Из дела «Аудита»/ }));
    click("Дальше");
    expect(await screen.findByText(/Нет доступа к делам «Аудита»/)).toBeTruthy();
  });
});
