// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AxiosError, AxiosHeaders } from "axios";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuditSubjectPage } from "./AuditSubjectPage";

/**
 * Упавшая загрузка дела — своё состояние (пакет J, J4). Прежде `isLoading` гас, данных
 * не было, и экран вечно показывал «Загрузка…»: человек ждал того, что не придёт.
 * Нашлось, когда состояния «Аудита» добавили в матрицу скриншотов.
 */

const getAuditSubject = vi.fn();

vi.mock("../api/audit", async (orig) => ({
  ...(await orig<typeof import("../api/audit")>()),
  getAuditSubject: (...a: unknown[]) => getAuditSubject(...a),
}));
vi.mock("../components/Toast", () => ({ useToast: () => vi.fn() }));

afterEach(cleanup);

function refused(status: number, detail: string): AxiosError {
  const headers = new AxiosHeaders();
  return new AxiosError("refused", String(status), { headers }, null, {
    status, statusText: "", headers, config: { headers }, data: { detail },
  });
}

function show() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/audit/s1"]}>
        <Routes><Route path="/audit/:id" element={<AuditSubjectPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Дело: загрузка не удалась", () => {
  it("показывает отказ с причиной сервера и два выхода, а не вечную загрузку", async () => {
    getAuditSubject.mockRejectedValue(refused(404, "Субъект не найден"));
    show();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не удалось загрузить дело");
    expect(alert.textContent).toContain("Субъект не найден");
    expect(screen.getByRole("button", { name: "← К делам" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Повторить" })).toBeTruthy();
    expect(screen.queryByText("Загрузка дела…")).toBeNull();
  });

  it("пока дело грузится — карточка загрузки со статусом для диктора", async () => {
    getAuditSubject.mockReturnValue(new Promise(() => undefined));
    show();
    expect((await screen.findByRole("status")).textContent).toContain("Загрузка дела…");
  });
});
