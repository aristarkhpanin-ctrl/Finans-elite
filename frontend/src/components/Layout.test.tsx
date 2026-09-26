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
    expect(screen.getByText("Дела")).toBeTruthy();
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
    fireEvent.click(screen.getByText("Участники и тариф"));
    expect(screen.getByText("Экран организации")).toBeTruthy();
    expect(document.documentElement.getAttribute("data-product")).toBe("audit");
  });
});

/**
 * Боковая навигация «Финанс Аудит» (макет Экран 6). Каркас общий на два продукта,
 * поэтому проверяется главное: рейл появляется только там, где он предусмотрен, и
 * навигация не оказывается на экране дважды.
 */
describe("Рейл продукта", () => {
  const rail = () => screen.queryByLabelText("Разделы продукта");

  it("у аудита есть, у бизнес-плана нет", () => {
    renderShell("/audit");
    expect(rail()).toBeTruthy();
    cleanup();
    renderShell("/projects");
    expect(rail()).toBeNull();
  });

  it("разделы и пункты — из описания продукта", () => {
    renderShell("/audit");
    for (const text of ["Работа", "Дела", "Группа", "Организация", "Участники и тариф"]) {
      expect(screen.getByText(text), `в рейле нет «${text}»`).toBeTruthy();
    }
  });

  it("навигация не дублируется: при рейле её нет в шапке", () => {
    renderShell("/audit");
    // «Дела» — один раз. Спрятанный второй экземпляр в шапке был бы вторым
    // одинаковым меню для скринридера и для поиска по странице.
    expect(screen.getAllByText("Дела")).toHaveLength(1);
    expect(document.querySelector(".shell-nav")).toBeNull();
    cleanup();
    // у продукта без рейла навигация, наоборот, обязана быть в шапке
    renderShell("/projects");
    expect(document.querySelector(".shell-nav")).toBeTruthy();
  });

  it("активный пункт подсвечен ровно один", () => {
    renderShell("/audit");
    const active = document.querySelectorAll(".rail__item--active");
    expect(active).toHaveLength(1);
    expect(active[0].textContent).toContain("Дела");
  });

  it("«Дела» не горят на вложенном разделе группы", () => {
    // /audit/group вложен в /audit: без end на родителе подсветились бы оба пункта
    renderShell("/audit/group");
    const active = document.querySelectorAll(".rail__item--active");
    expect(active).toHaveLength(1);
    expect(active[0].textContent).toContain("Группа");
  });

  it("переход по пункту рейла работает", () => {
    renderShell("/audit");
    fireEvent.click(screen.getByText("Группа"));
    expect(screen.getByText("Экран группы")).toBeTruthy();
  });
});
