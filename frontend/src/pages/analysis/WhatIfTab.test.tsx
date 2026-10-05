// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WhatIfTab } from "./WhatIfTab";

/** Пустой What-If называет, почему сравнивать нечего (матрица состояний, пакет I). */

vi.mock("../../api/analysis", async (orig) => ({
  ...(await orig<typeof import("../../api/analysis")>()),
  runWhatIf: vi.fn(),
}));

afterEach(cleanup);

describe("What-If без сценариев", () => {
  it("кнопка недоступна, причина названа", () => {
    render(<QueryClientProvider client={new QueryClient()}><WhatIfTab projectId="p1" /></QueryClientProvider>);
    const compare = screen.getByRole("button", { name: "Сравнить" });
    expect(compare.hasAttribute("disabled")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /Удалить сценарий/ }));
    expect(screen.getByRole("button", { name: "Сравнить" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Сценариев нет/)).toBeTruthy();
  });
});
