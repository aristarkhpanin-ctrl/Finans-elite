// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectsPage } from "./ProjectsPage";

/** Пустой список проектов ведёт в мастер первого проекта (G12); быстрое создание — рядом. */

const listProjects = vi.fn();
vi.mock("../api/projects", async (orig) => ({
  ...(await orig<typeof import("../api/projects")>()),
  listProjects: () => listProjects(),
  listTemplates: () => Promise.resolve([]),
}));

vi.mock("../components/CubeHero", () => ({ CubeHero: () => <div data-testid="cube" /> }));

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

function show() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/projects"]}>
        <Routes>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/onboarding" element={<div>Мастер первого проекта</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Список проектов", () => {
  it("пустой — ведёт в мастер, а быстрое создание остаётся", async () => {
    listProjects.mockResolvedValue([]);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Начать с мастера" }));
    expect(screen.getByText("Мастер первого проекта")).toBeTruthy();
  });

  it("непустой — мастер не навязывается", async () => {
    listProjects.mockResolvedValue([{
      id: "p1", name: "Завод", status: "draft", created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z", last_calc: null, is_stale: false,
    }]);
    show();
    expect(await screen.findByText("Завод")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Начать с мастера" })).toBeNull();
    expect(screen.getByRole("button", { name: /Создать пустой/ })).toBeTruthy();
  });
});
