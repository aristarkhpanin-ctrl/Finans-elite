// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuditOnboardingPage, defaultLabels, inviteLink } from "./AuditOnboardingPage";

/**
 * Онбординг. Проверяются решения, которые легко потерять при следующей правке экрана:
 * мастер заводит настоящее дело одним запросом в конце, обещания макета (ФНС по ИНН,
 * глубина проверки, доступ к делу, фоновый скан с письмом) на экран не вернулись, а
 * приглашение отдаёт ссылку, потому что писем платформа не шлёт.
 */

const createAuditSubject = vi.fn();
vi.mock("../api/audit", async (orig) => ({
  ...(await orig<typeof import("../api/audit")>()),
  createAuditSubject: (...a: unknown[]) => createAuditSubject(...a),
}));

const addMember = vi.fn();
vi.mock("../api/org", async (orig) => ({
  ...(await orig<typeof import("../api/org")>()),
  addMember: (...a: unknown[]) => addMember(...a),
}));

let role = "owner";
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ organizations: [{ id: "o1", name: "Орг", role }], currentOrgId: "o1" }),
}));

// Куб-марка — анимированная сцена на RAF; в тесте она не нужна и только шумит.
vi.mock("../components/CubeHero", () => ({ CubeHero: () => <div data-testid="cube" /> }));

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  role = "owner";
  createAuditSubject.mockResolvedValue({ id: "s1", name: "ООО «Пример»" });
});

function show() {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    })}>
      <MemoryRouter initialEntries={["/audit/onboarding"]}>
        <Routes>
          <Route path="/audit/onboarding" element={<AuditOnboardingPage />} />
          <Route path="/audit" element={<div>Список дел</div>} />
          <Route path="/audit/:id" element={<div>Карточка дела</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const fill = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
const click = (name: RegExp | string) =>
  fireEvent.click(screen.getByRole("button", { name }));

/** Пройти первый шаг: без названия «Дальше» заблокирована. */
function step1(name = "ООО «Пример»") {
  fill("Название фирмы-цели", name);
  click("Дальше");
}

describe("Подписи периодов", () => {
  it("годы — последние завершённые, по возрастанию", () => {
    // Отчётность за идущий год ещё не сдана: предлагать его — звать ввести то,
    // чего у пользователя нет.
    expect(defaultLabels("year", 3, new Date("2026-09-06")))
      .toEqual(["2023", "2024", "2025"]);
  });

  it("кварталы и месяцы не угадываются", () => {
    expect(defaultLabels("quarter", 2)).toEqual(["", ""]);
  });
});

describe("Онбординг", () => {
  it("обещания ФНС по ИНН на экране нет, и сказано почему", () => {
    show();
    expect(screen.queryByLabelText(/ИНН/)).toBeNull();
    expect(screen.getByText(/интеграции с ФНС у платформы нет/)).toBeTruthy();
  });

  it("глубины проверки не предлагается", () => {
    // «Экспресс · 8 / Полная · 24 / Для банка · 31» — пресетов нет: чек-лист один
    // на все дела, а сокращённый набор лишь спрятал бы работу.
    show();
    expect(document.body.textContent).not.toMatch(/Экспресс|Глубина проверки|Для банка/);
  });

  it("без названия дальше не пускает", () => {
    show();
    expect(screen.getByRole("button", { name: "Дальше" })).toHaveProperty("disabled", true);
  });

  it("периоды предлагаются годами и правятся вручную", () => {
    show();
    step1();
    expect(screen.getByLabelText("Подпись периода 1")).toHaveProperty("value",
      defaultLabels("year", 3)[0]);
    fireEvent.change(screen.getByLabelText("Сколько периодов"), { target: { value: "2" } });
    expect(screen.getAllByLabelText(/Подпись периода/)).toHaveLength(2);
  });

  it("смена периодичности не оставляет угаданных годов", () => {
    show();
    step1();
    fireEvent.change(screen.getByLabelText("Периодичность"), { target: { value: "quarter" } });
    expect(screen.getByLabelText("Подпись периода 1")).toHaveProperty("value", "");
  });

  it("права называются организационными, а не «доступом к делу»", () => {
    show();
    step1();
    click("Дальше");
    expect(screen.getByText(/Отдельного доступа к делу в продукте нет/)).toBeTruthy();
  });

  it("дело заводится одним запросом в конце — с периодами и реквизитами", async () => {
    show();
    fill("Название фирмы-цели", "ООО «Пример»");
    fill("Отрасль", "Перевозки");
    click("Дальше");
    fireEvent.change(screen.getByLabelText("Сколько периодов"), { target: { value: "2" } });
    click("Дальше");
    // До последней кнопки дело не заводится: брошенный мастер не оставляет
    // полупустых дел.
    expect(createAuditSubject).not.toHaveBeenCalled();
    click("Завести дело");
    await waitFor(() => expect(createAuditSubject).toHaveBeenCalledTimes(1));
    const [name, model] = createAuditSubject.mock.calls[0];
    expect(name).toBe("ООО «Пример»");
    expect(model.industry).toBe("Перевозки");
    expect(model.periods).toHaveLength(2);
    expect(model.periods[0].kind).toBe("year");
  });

  it("после создания сказано, что скана и письма не будет", async () => {
    show();
    step1();
    click("Дальше");
    click("Завести дело");
    await screen.findByText(/Фонового скана нет и письма не будет/);
    // Имя дела — заголовок, а не вставка в предложение (иначе кавычки в кавычках).
    expect(document.querySelector(".onb__title")!.textContent).toBe("ООО «Пример»");
  });

  it("готовое дело открывается по кнопке", async () => {
    show();
    step1();
    click("Дальше");
    click("Завести дело");
    await screen.findByRole("button", { name: "Открыть дело" });
    click("Открыть дело");
    expect(screen.getByText("Карточка дела")).toBeTruthy();
  });

  it("приглашение отдаёт ссылку, а не обещает письмо", async () => {
    addMember.mockResolvedValue({ user_id: "u2", email: "k@e.ru", full_name: "Коллега",
                                  role: "analyst", invite_token: "tok" });
    show();
    step1();
    click("Дальше");
    fill("Почта коллеги", "k@e.ru");
    click("Добавить участника");
    await screen.findByLabelText("Ссылка приглашения для k@e.ru");
    expect(screen.getByText(/Писем платформа не отправляет/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/приглашение отправлено/i);
  });

  it("участнику с паролем ссылка не выдаётся", async () => {
    // Токена в ответе нет — вечного пропуска в чужой аккаунт на экране не появится.
    addMember.mockResolvedValue({ user_id: "u2", email: "k@e.ru", full_name: "",
                                  role: "analyst", invite_token: null });
    show();
    step1();
    click("Дальше");
    fill("Почта коллеги", "k@e.ru");
    click("Добавить участника");
    await screen.findByText(/Пароль у участника уже есть/);
    expect(screen.queryByLabelText(/Ссылка приглашения/)).toBeNull();
  });

  it("без прав форма приглашения не показывается, и сказано почему", () => {
    role = "analyst";
    show();
    step1();
    click("Дальше");
    expect(screen.queryByLabelText("Почта коллеги")).toBeNull();
    expect(screen.getByText(/может владелец или администратор/)).toBeTruthy();
  });

  it("отказ сервера в приглашении назван причиной", async () => {
    addMember.mockRejectedValue({ isAxiosError: true, response: { status: 402 } });
    show();
    step1();
    click("Дальше");
    fill("Почта коллеги", "k@e.ru");
    click("Добавить участника");
    await screen.findByText("Достигнут лимит участников тарифа");
  });

  it("настройку можно пропустить", () => {
    show();
    click("Пропустить настройку");
    expect(screen.getByText("Список дел")).toBeTruthy();
  });
});

describe("Ссылка активации", () => {
  it("собирается из адреса приложения и токена", () => {
    expect(inviteLink("tok", "https://app.test")).toBe("https://app.test/activate?token=tok");
  });
});
