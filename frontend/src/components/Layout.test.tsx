// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Layout } from "./Layout";

/**
 * Переключатель продукта — единственная дорога во второй продукт. Если он не работает,
 * «Финанс-Аудит» недостижим целиком, поэтому дорога проверяется тестом, а не на глаз.
 */

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "u1", email: "a@e.ru", full_name: "Аудитор" },
    organizations: [{ id: "o1", name: "Орг", role: "owner" }],
    currentOrgId: "o1",
    loading: false,
    login: vi.fn(), register: vi.fn(), logout: vi.fn(), selectOrg: vi.fn(),
  }),
}));

// Куб-марка — анимированная сцена на RAF; в тесте она не нужна и только шумит.
vi.mock("./CubeHero", () => ({ CubeHero: () => <div data-testid="cube" /> }));

afterEach(cleanup);
beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-product");
});

/** Отрисовать оболочку на заданном маршруте; страницы подменены заглушками. */
function renderShell(path = "/projects") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/projects" element={<div>Экран проектов</div>} />
          <Route path="/audit" element={<div>Экран субъектов аудита</div>} />
          <Route path="/audit/group" element={<div>Экран группы</div>} />
          <Route path="/organization" element={<div>Экран организации</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

const switcher = () => screen.getByTitle("Переключить продукт");

describe("Переключатель продукта", () => {
  it("на проектах активен «Финанс-Элит»: бренд, навигация и зелёная тема", () => {
    renderShell("/projects");
    expect(switcher().textContent).toContain("Бизнес-план");
    expect(screen.getByText("-Элит")).toBeTruthy();
    expect(screen.getByText("Проекты")).toBeTruthy();
    expect(document.documentElement.getAttribute("data-product")).toBeNull();
  });

  it("клик по кнопке раскрывает меню с обоими продуктами", () => {
    renderShell("/projects");
    expect(screen.queryByText("Финанс-Аудит")).toBeNull();
    fireEvent.click(switcher());
    expect(screen.getByText("Финанс-Элит")).toBeTruthy();
    expect(screen.getByText("Финанс-Аудит")).toBeTruthy();
    expect(switcher().getAttribute("aria-expanded")).toBe("true");
  });

  it("выбор «Финанс-Аудит» переводит на его раздел и включает фиолетовую тему", () => {
    renderShell("/projects");
    fireEvent.click(switcher());
    fireEvent.click(screen.getByText("Финанс-Аудит"));

    expect(screen.getByText("Экран субъектов аудита")).toBeTruthy();
    expect(document.documentElement.getAttribute("data-product")).toBe("audit");
    expect(switcher().textContent).toContain("Аудит");
    expect(screen.getByText("-Аудит")).toBeTruthy();
    // навигация тоже продуктовая
    expect(screen.getByText("Субъекты")).toBeTruthy();
    expect(screen.queryByText("Проекты")).toBeNull();
  });

  it("обратный переход возвращает бизнес-план и снимает тему аудита", () => {
    renderShell("/audit");
    expect(document.documentElement.getAttribute("data-product")).toBe("audit");
    fireEvent.click(switcher());
    fireEvent.click(screen.getByText("Финанс-Элит"));

    expect(screen.getByText("Экран проектов")).toBeTruthy();
    expect(document.documentElement.getAttribute("data-product")).toBeNull();
  });

  it("меню закрывается после выбора", () => {
    renderShell("/projects");
    fireEvent.click(switcher());
    fireEvent.click(screen.getByText("Финанс-Аудит"));
    expect(switcher().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("Анализ фактической отчётности")).toBeNull();
  });

  it("общий раздел сохраняет выбранный продукт, а не сбрасывает тему", () => {
    // выбрали аудит → ушли в «Организацию»: тема не должна «прыгнуть» на зелёную
    renderShell("/audit");
    fireEvent.click(screen.getByText("Организация"));
    expect(screen.getByText("Экран организации")).toBeTruthy();
    expect(document.documentElement.getAttribute("data-product")).toBe("audit");
  });
});
