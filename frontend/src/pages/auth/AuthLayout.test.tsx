// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AxiosError } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "../LoginPage";
import { RegisterPage } from "../RegisterPage";

/**
 * Вход и регистрация. Проверяется то, что различает два продукта на общем каркасе:
 * марка и обещания панели, тема, куда ведёт успешный вход, — и отказы от обещаний
 * макета «Экран 3», которых в продукте нет (скан за шесть минут, статистика дисконта,
 * восстановление пароля, именной счётчик попыток).
 */

const login = vi.fn();
const registerFn = vi.fn();
vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({ login, register: registerFn }),
}));

const getCapabilities = vi.fn();
const requestPasswordReset = vi.fn();
vi.mock("../../api/auth", async (orig) => ({
  ...(await orig<typeof import("../../api/auth")>()),
  getCapabilities: (...a: unknown[]) => getCapabilities(...a),
  requestPasswordReset: (...a: unknown[]) => requestPasswordReset(...a),
}));

// Куб-марка — анимированная сцена на RAF; в тесте она не нужна и только шумит.
vi.mock("../../components/CubeHero", () => ({ CubeHero: () => <div data-testid="cube" /> }));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  document.documentElement.removeAttribute("data-product");
});

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  login.mockResolvedValue(undefined);
  registerFn.mockResolvedValue(undefined);
  // По умолчанию почта в установке не настроена — как и в свежем развёртывании.
  getCapabilities.mockResolvedValue({ mail: false });
  requestPasswordReset.mockResolvedValue(
    "Если такая учётная запись у нас есть, письмо со ссылкой уже в пути.");
});

/** Ошибка в том виде, в каком её отдаёт клиент: httpStatus читает признак axios. */
function httpError(status: number): AxiosError {
  const e = new AxiosError("fail");
  e.response = { status, data: {}, statusText: "", headers: {},
                 config: e.config ?? ({} as never) };
  return e;
}

function show(page: "login" | "register", product?: "audit" | "business") {
  if (product) localStorage.setItem("fe_product", product);
  const Page = page === "login" ? LoginPage : RegisterPage;
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <MemoryRouter initialEntries={["/" + page]}>
        <Routes>
          <Route path={"/" + page} element={<Page />} />
          <Route path="/projects" element={<div>Список проектов</div>} />
          <Route path="/audit" element={<div>Список дел</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const fill = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

/** Дождаться редиректа: сначала промис входа, затем прогресс success-оверлея. */
async function settle() {
  await act(async () => { await Promise.resolve(); });
  await act(async () => { vi.advanceTimersByTime(2000); });
}

const wordmark = () => document.querySelector(".auth-brand__word")!.textContent;

describe("Вход", () => {
  it("открывается в том продукте, из которого ушли", () => {
    // У «/login» своего продукта нет: зелёный экран со словом «-Элит» после выхода
    // из «Аудита» — это вход в другой продукт.
    show("login", "audit");
    expect(wordmark()).toBe("Финанс-Аудит");
    expect(document.documentElement.getAttribute("data-product")).toBe("audit");
    expect(screen.getByText(/делами и заключениями/)).toBeTruthy();
  });

  it("по умолчанию — бизнес-план, тема продукта не проставлена", () => {
    show("login");
    expect(wordmark()).toBe("Финанс-Элит");
    expect(document.documentElement.getAttribute("data-product")).toBeNull();
    expect(screen.getByText(/моделями и отчётами/)).toBeTruthy();
  });

  it("панель аудита не обещает скана и чужой статистики", () => {
    // В макете — «24 процедуры», «06:00 среднее время скана», «18% средний дисконт
    // к цене». Фонового скана в продукте нет, статистики по чужим сделкам — тоже.
    show("login", "audit");
    const panel = document.querySelector(".auth-brand")!.textContent!;
    expect(panel).not.toMatch(/24 процедур|06:00|скан/i);
    expect(panel).not.toMatch(/дисконт|средн/i);
    expect(panel).toContain("Реестр флагов, качество прибыли, обязательства");
  });

  it("без почты забывшему пароль назван реальный путь, а не ссылка в никуда", async () => {
    // Самостоятельного сброса без письма нет, но тупика тоже нет: ссылку выдаёт
    // администратор организации — так и написано под полем.
    show("login");
    expect(screen.getByText(/ссылку на сброс выдаёт администратор организации/)).toBeTruthy();
    await waitFor(() => expect(getCapabilities).toHaveBeenCalled());
    // И ссылки, ведущей в тупик, при этом нет.
    expect(screen.queryByRole("button", { name: "Забыли пароль?" })).toBeNull();
  });

  it("с почтой появляется «Забыли пароль?» и говорит, куда уйдёт ссылка", async () => {
    getCapabilities.mockResolvedValue({ mail: true });
    show("login");
    fireEvent.click(await screen.findByRole("button", { name: "Забыли пароль?" }));
    const dialog = within(screen.getByRole("dialog"));
    // Ссылка уходит **в ящик**, а не просившему — на этом и держится безопасность.
    expect(dialog.getByText(/на сам почтовый ящик/)).toBeTruthy();
    // И письмо не заменяет второй фактор: иначе он выключался бы первым же письмом.
    expect(dialog.getByText(/письмо его не заменяет/)).toBeTruthy();
  });

  it("ответ сервера показывается как есть — он один на любой адрес", async () => {
    getCapabilities.mockResolvedValue({ mail: true });
    show("login");
    fireEvent.click(await screen.findByRole("button", { name: "Забыли пароль?" }));
    const dialog = within(screen.getByRole("dialog"));
    fireEvent.change(dialog.getByLabelText("Email"), { target: { value: "a@e.ru" } });
    fireEvent.click(dialog.getByRole("button", { name: "Прислать ссылку" }));

    await waitFor(() => expect(requestPasswordReset).toHaveBeenCalledWith("a@e.ru"));
    // «Письмо отправлено на ваш адрес» было бы утверждением, которого сервер намеренно
    // не делает: оно сказало бы, что такой адрес у платформы есть.
    expect(await screen.findByText(/Если такая учётная запись у нас есть/)).toBeTruthy();
  });

  it("слишком частые попытки объяснены без именного счётчика", async () => {
    // «Осталось 3 попытки до блокировки» обещало бы счёт по учётной записи; сервер
    // считает попытки с адреса за минуту.
    login.mockRejectedValue(httpError(429));
    show("login");
    fill("Email", "a@e.ru");
    fill("Пароль", "secret12");
    fireEvent.click(screen.getByRole("button", { name: /Войти/ }));
    await act(async () => { await Promise.resolve(); });
    const banner = screen.getByRole("alert").textContent!;
    expect(banner).toContain("Подождите минуту");
    expect(banner).not.toMatch(/попыт\w+ до блокировки/);
  });

  it("неверная пара названа отдельно от сбоя связи", async () => {
    login.mockRejectedValue(httpError(401));
    show("login");
    fill("Email", "a@e.ru");
    fill("Пароль", "secret12");
    fireEvent.click(screen.getByRole("button", { name: /Войти/ }));
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole("alert").textContent).toContain("Неверный email или пароль");
  });

  it("успешный вход ведёт в продукт, из которого пришли", async () => {
    vi.useFakeTimers();
    show("login", "audit");
    fill("Email", "a@e.ru");
    fill("Пароль", "secret12");
    fireEvent.click(screen.getByRole("button", { name: /Войти/ }));
    await settle();
    expect(screen.getByText("Список дел")).toBeTruthy();
  });

  it("вход из бизнес-плана остаётся в бизнес-плане", async () => {
    vi.useFakeTimers();
    show("login");
    fill("Email", "a@e.ru");
    fill("Пароль", "secret12");
    fireEvent.click(screen.getByRole("button", { name: /Войти/ }));
    await settle();
    expect(screen.getByText("Список проектов")).toBeTruthy();
  });
});

describe("Регистрация", () => {
  it("новая организация открывается в том же продукте", async () => {
    vi.useFakeTimers();
    show("register", "audit");
    expect(wordmark()).toBe("Финанс-Аудит");
    expect(screen.getByText(/дел о фирмах-целях/)).toBeTruthy();
    fill("ФИО", "Иван Петров");
    fill("Email", "a@e.ru");
    fill("Пароль", "secret12");
    fill("Название организации", "ООО «Пример»");
    fireEvent.click(screen.getByRole("button", { name: /Создать аккаунт/ }));
    await settle();
    expect(screen.getByText("Список дел")).toBeTruthy();
  });
});
