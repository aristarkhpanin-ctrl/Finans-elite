// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, render, screen } from "@testing-library/react";
import { useEffect, useState } from "react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ANNOUNCE_MAX_WAIT_MS, ANNOUNCE_SETTLE_MS, RouteAnnouncer } from "./components/RouteAnnouncer";
import { pageTitle, usePageTitle } from "./pageTitle";

/**
 * Заголовок страницы и объявление перехода (пакет K, K5). У всех маршрутов был один
 * заголовок «Финансовая модель», и переход в одностраничном приложении был беззвучен:
 * диктор не мог сказать, где человек оказался.
 */

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

// В jsdom `import.meta.url` — не файловый адрес; vitest запускается из корня фронта.
const root = join(process.cwd(), "src") + "/";

describe("заголовок документа", () => {
  it("части через тире, продукт последним, пустое пропускается", () => {
    window.history.replaceState(null, "", "/projects/1/results");
    expect(pageTitle("Результаты", "Кофейня")).toBe("Результаты — Кофейня — Финанс-Элит");
    expect(pageTitle("Результаты", "", null, undefined)).toBe("Результаты — Финанс-Элит");
    window.history.replaceState(null, "", "/audit/7");
    expect(pageTitle("Дело", "ООО «Ромашка»")).toBe("Дело — ООО «Ромашка» — Финанс-Аудит");
  });

  it("каждая страница маршрута ставит свой заголовок", () => {
    // Страница без заголовка унаследовала бы заголовок предыдущей — и диктор объявил бы
    // не ту страницу. Перечень — из самих маршрутов (App.tsx), а не списком в тесте.
    const app = readFileSync(root + "App.tsx", "utf8");
    const pages = [...app.matchAll(/["(]\.\/pages\/(\w+)[")]/g)].map((m) => m[1]);
    expect(pages.length).toBeGreaterThan(15);
    const missing = pages.filter((page) =>
      !readFileSync(`${root}pages/${page}.tsx`, "utf8").includes("usePageTitle("));
    expect(missing, "страница без usePageTitle").toEqual([]);
  });
});

function Page({ title, to }: { title: string; to?: string }) {
  usePageTitle(title);
  const navigate = useNavigate();
  return to ? <button type="button" onClick={() => navigate(to)}>дальше</button> : null;
}

describe("объявление перехода", () => {
  function show() {
    window.history.replaceState(null, "", "/projects");
    render(
      <MemoryRouter initialEntries={["/projects"]}>
        <Routes>
          <Route path="/projects" element={<Page title="Проекты" to="/holdings" />} />
          <Route path="/holdings" element={<Page title="Холдинги" />} />
        </Routes>
        <RouteAnnouncer />
      </MemoryRouter>,
    );
  }

  it("первая загрузка не объявляется — заголовок диктор читает сам", () => {
    vi.useFakeTimers();
    show();
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MAX_WAIT_MS * 2); });
    expect(screen.getByTestId("route-announcer").textContent).toBe("");
    expect(document.title).toBe("Проекты — Финанс-Элит");
  });

  it("после перехода живая область называет новую страницу", () => {
    vi.useFakeTimers();
    show();
    act(() => { screen.getByRole("button", { name: "дальше" }).click(); });
    act(() => { vi.advanceTimersByTime(ANNOUNCE_SETTLE_MS + 10); });
    const live = screen.getByTestId("route-announcer");
    expect(live.getAttribute("aria-live")).toBe("polite");
    expect(live.textContent).toBe("Открыта страница: Холдинги — Финанс-Элит");
  });

  it("медленная страница объявляется своим заголовком, а не прежним", () => {
    // Ленивая страница результатов ставит заголовок позже перехода: объявлять то, что
    // стоит через фиксированную паузу, значило бы назвать предыдущую страницу.
    vi.useFakeTimers();
    window.history.replaceState(null, "", "/projects");
    function Slow() {
      const [ready, setReady] = useState(false);
      useEffect(() => { const id = window.setTimeout(() => setReady(true), 1000); return () => window.clearTimeout(id); }, []);
      return ready ? <Page title="Результаты" /> : null;
    }
    render(
      <MemoryRouter initialEntries={["/projects"]}>
        <Routes>
          <Route path="/projects" element={<Page title="Проекты" to="/results" />} />
          <Route path="/results" element={<Slow />} />
        </Routes>
        <RouteAnnouncer />
      </MemoryRouter>,
    );
    act(() => { screen.getByRole("button", { name: "дальше" }).click(); });
    act(() => { vi.advanceTimersByTime(500); });
    expect(screen.getByTestId("route-announcer").textContent).toBe("");
    act(() => { vi.advanceTimersByTime(500); });              // страница встала и назвалась
    act(() => { vi.advanceTimersByTime(ANNOUNCE_SETTLE_MS + 10); });
    expect(screen.getByTestId("route-announcer").textContent)
      .toBe("Открыта страница: Результаты — Финанс-Элит");
  });
});
