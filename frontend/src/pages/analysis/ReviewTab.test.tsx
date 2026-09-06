// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReviewResponse } from "../../api/review";
import { ReviewTab } from "./ReviewTab";

const review: ReviewResponse = {
  light: "risk",
  counts: { risk: 1, warning: 1, info: 0 },
  deep: true,
  opinion: "Ревью выявило существенные риски.\n\nИтог: план не рекомендуется без доработки.",
  findings: [
    {
      id: "viability.npv_negative", category: "viability", severity: "risk",
      title: "Отрицательный NPV", detail: "NPV меньше нуля.",
      recommendation: "Пересмотрите допущения.", confidence: "high", evidence: { npv: "-100" },
    },
    {
      id: "liquidity.overleverage", category: "liquidity", severity: "warning",
      title: "Высокий рычаг", detail: "Долг велик.",
      recommendation: "Снизьте займы.", confidence: "high", evidence: {},
    },
  ],
};

vi.mock("../../api/review", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/review")>()),
  getReview: vi.fn(async () => review),
  finalizeProject: vi.fn(async () => ({ status: "finalized", finalized_at: "2026-07-11", review })),
}));

vi.mock("../../api/projects", () => ({
  getProject: vi.fn(async () => ({
    id: "p1", name: "P", created_at: "", updated_at: "", model: {}, status: "draft",
  })),
}));

afterEach(cleanup);

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ReviewTab projectId="p1" />
    </QueryClientProvider>,
  );
}

describe("ReviewTab", () => {
  it("рендерит светофор и находки по severity", async () => {
    renderTab();
    expect(await screen.findByText("Найдены риски")).toBeTruthy();
    expect(screen.getByText("Отрицательный NPV")).toBeTruthy();
    expect(screen.getByText("Высокий рычаг")).toBeTruthy();
  });

  it("показывает экспертное заключение (автотекст)", async () => {
    renderTab();
    expect(await screen.findByText("Экспертное заключение")).toBeTruthy();
    expect(screen.getByText(/план не рекомендуется без доработки/)).toBeTruthy();
  });

  it("гейт: риск блокирует финализацию до подтверждения", async () => {
    renderTab();
    const btn = (await screen.findByRole("button", { name: /Финализировать план/ })) as HTMLButtonElement;
    expect(btn.disabled).toBe(true); // risk > 0 → заблокировано
    fireEvent.click(screen.getByRole("checkbox")); // подтвердить осознание рисков
    const after = screen.getByRole("button", { name: /Финализировать план/ }) as HTMLButtonElement;
    expect(after.disabled).toBe(false);
  });
});
