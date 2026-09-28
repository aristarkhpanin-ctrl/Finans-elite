// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { AxiosError } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MonteCarloTab } from "./MonteCarloTab";

/**
 * Отказ запуска Монте-Карло (матрица состояний, пакет I). Съёмка показала два дефекта
 * сразу: под ошибкой висело приглашение «Запустите симуляцию» — будто ничего не
 * произошло, — а текст ошибки был догадкой («проверьте распределения»), хотя сервер
 * назвал причину.
 */

const submit = vi.fn();
vi.mock("../../api/analysis", async (orig) => ({
  ...(await orig<typeof import("../../api/analysis")>()),
  submitMonteCarloAsync: (...a: unknown[]) => submit(...a),
}));
vi.mock("../../components/CubeHero", () => ({ CubeHero: () => <div /> }));

afterEach(cleanup);

function refusal(detail: string): AxiosError {
  const e = new AxiosError("fail");
  e.response = { status: 503, data: { detail }, statusText: "", headers: {},
                 config: e.config ?? ({} as never) };
  return e;
}

describe("Монте-Карло: отказ запуска", () => {
  it("причину называет сервер, приглашения запустить рядом нет", async () => {
    submit.mockRejectedValue(refusal("Сервис временно недоступен"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={qc}><MonteCarloTab projectId="p1" /></QueryClientProvider>);
    expect(screen.getByText("Запустите симуляцию")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Запустить" }));
    expect(await screen.findByText("Не удалось выполнить симуляцию")).toBeTruthy();
    expect(screen.getByText("Сервис временно недоступен")).toBeTruthy();
    expect(screen.queryByText("Запустите симуляцию")).toBeNull();
  });
});
