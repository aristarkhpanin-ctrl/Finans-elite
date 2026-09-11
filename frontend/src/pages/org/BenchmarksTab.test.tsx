// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Benchmark } from "../../api/org";
import { BenchmarksTab } from "./BenchmarksTab";

/**
 * Справочник отраслевых ориентиров организации (Прил. Ф).
 *
 * Проверяется то, что делает справочник честным: строка без числа не сохраняется
 * (ориентира без значения не бывает), справочник пишется целиком (что на экране, то и
 * в хранилище), отказ сервера показывается его же словами, а тот, кто не управляет
 * организацией, видит содержимое, но не правит его — недоступное показывается, а не
 * исчезает.
 */

const getBenchmarks = vi.fn();
const putBenchmarks = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getBenchmarks: (...a: unknown[]) => getBenchmarks(...a),
  putBenchmarks: (...a: unknown[]) => putBenchmarks(...a),
}));

const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));

const row = (over: Partial<Benchmark> = {}): Benchmark => ({
  id: "b1", industry: "Перевозки", metric: "ev_ebitda", value: "5.0",
  source: "медиана по 3 сделкам фонда", updated_at: "2026-09-01T10:00:00Z", ...over,
} as Benchmark);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getBenchmarks.mockResolvedValue([row()]);
  putBenchmarks.mockResolvedValue([row()]);
});

async function show(canManage = true) {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <BenchmarksTab orgId="o1" canManage={canManage} />
    </QueryClientProvider>,
  );
  await screen.findByDisplayValue("Перевозки");
}

describe("Справочник отраслевых ориентиров", () => {
  it("показывает заведённые ориентиры вместе с источником", async () => {
    await show();
    expect(screen.getByDisplayValue("медиана по 3 сделкам фонда")).toBeTruthy();
    expect(screen.getByText("01.09.2026")).toBeTruthy();
  });

  it("справочник записывается целиком — что на экране, то и сохранено", async () => {
    await show();
    fireEvent.change(screen.getByLabelText("Ориентир, строка 1"),
                     { target: { value: "6.5" } });
    fireEvent.click(screen.getByText("Сохранить"));
    await waitFor(() => expect(putBenchmarks).toHaveBeenCalledWith("o1", [
      { industry: "Перевозки", metric: "ev_ebitda", value: "6.5",
        source: "медиана по 3 сделкам фонда" },
    ]));
  });

  it("пустая строка не сохраняется: ориентира без числа не бывает", async () => {
    await show();
    fireEvent.click(screen.getByText(/Добавить ориентир/));
    fireEvent.change(screen.getByLabelText("Отрасль, строка 2"),
                     { target: { value: "Торговля" } });
    fireEvent.click(screen.getByText("Сохранить"));
    await waitFor(() => expect(putBenchmarks).toHaveBeenCalled());
    expect(putBenchmarks.mock.calls[0][1]).toHaveLength(1);
  });

  it("удалённая строка исчезает из записи, а не из одного экрана", async () => {
    await show();
    fireEvent.click(screen.getByTitle("Удалить ориентир"));
    fireEvent.click(screen.getByText("Сохранить"));
    await waitFor(() => expect(putBenchmarks).toHaveBeenCalledWith("o1", []));
  });

  it("отказ сервера показывается его же словами", async () => {
    // Своя формулировка разошлась бы с правилом на бэкенде: там две строки на одну
    // пару «отрасль + база» запрещены, и причина названа в ответе.
    putBenchmarks.mockRejectedValue({
      isAxiosError: true,
      response: { status: 422, data: { detail: "Ориентир задан дважды" } },
    });
    await show();
    fireEvent.click(screen.getByText("Сохранить"));
    await waitFor(() => expect(toast)
      .toHaveBeenCalledWith("Ориентир задан дважды", { kind: "error" }));
  });

  it("без права на управление справочник виден, но не правится", async () => {
    await show(false);
    expect((screen.getByLabelText("Отрасль, строка 1") as HTMLInputElement).disabled)
      .toBe(true);
    expect(screen.queryByText("Сохранить")).toBeNull();
    expect(screen.getByText(/правят владелец и администратор/)).toBeTruthy();
  });

  it("пустой справочник объясняет, чем это обернётся в деле", async () => {
    getBenchmarks.mockResolvedValue([]);
    render(
      <QueryClientProvider client={new QueryClient({
        defaultOptions: { queries: { retry: false } },
      })}>
        <BenchmarksTab orgId="o1" canManage />
      </QueryClientProvider>,
    );
    expect((await screen.findByText(/сравнивать не с чем/)).textContent)
      .toContain("Оценка");
  });
});
