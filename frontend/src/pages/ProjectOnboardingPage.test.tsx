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
const listTemplates = vi.fn();
vi.mock("../api/projects", async (orig) => ({
  ...(await orig<typeof import("../api/projects")>()),
  createProject: (...a: unknown[]) => createProject(...a),
  createProjectFromTemplate: (...a: unknown[]) => createProjectFromTemplate(...a),
  listTemplates: () => listTemplates(),
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

  it("третьей цели («из дела „Аудита“») нет, пока нет моста между продуктами", () => {
    show();
    expect(screen.queryByText(/Аудит/)).toBeNull();
  });
});
