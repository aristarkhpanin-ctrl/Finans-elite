// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditVersionDiff, AuditVersionSummary } from "../api/audit";
import { AuditVersions } from "./AuditVersions";

/**
 * Версии дела. Проверяется то, ради чего снимок и делают: сводка в списке —
 * **сохранённая на тот момент**, вердикт назван словом, отсутствие отчётности не
 * выдаётся за «в норме», а диф говорит о деле (вердикт, находки, охват, цена), а не
 * сыплет коэффициентами.
 */

const listAuditVersions = vi.fn();
const diffAuditVersion = vi.fn();
const createAuditVersion = vi.fn();
vi.mock("../api/audit", async (orig) => ({
  ...(await orig<typeof import("../api/audit")>()),
  listAuditVersions: (...a: unknown[]) => listAuditVersions(...a),
  diffAuditVersion: (...a: unknown[]) => diffAuditVersion(...a),
  createAuditVersion: (...a: unknown[]) => createAuditVersion(...a),
}));

const toast = vi.fn();
vi.mock("./Toast", () => ({ useToast: () => toast }));

const version = (over: Partial<AuditVersionSummary> = {}): AuditVersionSummary => ({
  id: "v1", label: "Перед комитетом", created_at: "2026-09-01T10:00:00Z",
  verdict: "risk", risk_flags: 2, equity_value: "850000000", ...over,
} as AuditVersionSummary);

const diff = (over: Partial<AuditVersionDiff> = {}): AuditVersionDiff => ({
  base_id: "v1", against: "current",
  model_changes: [{ path: "income.I_REVENUE[1]", kind: "changed", old: "600", new: "1200" }],
  model_changes_truncated: false,
  metric_changes: [
    { key: "verdict", label: "Вердикт", old: "risk", new: "warning" },
    { key: "risk_flags", label: "Флагов риска", old: "2", new: "1" },
    { key: "coverage", label: "Охват проверки", old: "0.6", new: "0.6" },
    { key: "equity_value", label: "Стоимость доли", old: null, new: "900000000" },
  ],
  ...over,
} as AuditVersionDiff);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  listAuditVersions.mockResolvedValue([version()]);
  diffAuditVersion.mockResolvedValue(diff());
});

async function show() {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <AuditVersions subjectId="s1" />
    </QueryClientProvider>,
  );
  await screen.findByText("Перед комитетом");
}

describe("Версии дела", () => {
  it("в списке — сводка на момент снимка, вердикт словом", async () => {
    await show();
    const meta = document.querySelector(".vrow__meta")!.textContent!;
    expect(meta).toContain("Высокий риск");
    expect(meta).toContain("флагов риска 2");
  });

  it("снимок пустого дела не выдаётся за «в норме»", async () => {
    // `verdict === null` — отчётности тогда не было; «ok» здесь читался бы как
    // «проверено, всё хорошо».
    listAuditVersions.mockResolvedValue([
      version({ verdict: null, risk_flags: null, equity_value: null })]);
    await show();
    const meta = document.querySelector(".vrow__meta")!.textContent!;
    expect(meta).toContain("отчётности тогда не было");
    expect(meta).not.toContain("В норме");
  });

  it("диф показывает величины дела и правку отчётности", async () => {
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Сравнить с текущим" }));
    await screen.findByText("Что изменилось в деле");

    const rows = [...document.querySelectorAll(".contrib-row")].map((r) => r.textContent ?? "");
    expect(rows.find((r) => r.includes("Вердикт"))).toContain("Требует внимания");
    // Неизменные величины в список не идут: диф отвечает «что изменилось».
    expect(rows.some((r) => r.includes("Охват проверки"))).toBe(false);
    expect(screen.getByText("income.I_REVENUE[1]")).toBeTruthy();
  });

  it("непосчитанная прежде величина показана прочерком, а не нулём", async () => {
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Сравнить с текущим" }));
    await screen.findByText("Что изменилось в деле");
    const row = [...document.querySelectorAll(".contrib-row")]
      .find((r) => r.textContent?.includes("Стоимость доли"))!;
    expect(row.textContent).toContain("—");
  });

  it("пустой список зовёт сохранить версию перед выдачей заключения", async () => {
    listAuditVersions.mockResolvedValue([]);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuditVersions subjectId="s1" />
      </QueryClientProvider>,
    );
    await screen.findByText("Версий пока нет");
    expect(screen.getByText(/вернуться к подписанному состоянию/)).toBeTruthy();
  });

  it("снимок сохраняется с введённым названием", async () => {
    createAuditVersion.mockResolvedValue(version());
    await show();
    fireEvent.change(screen.getByLabelText("Название версии"),
                     { target: { value: "Для банка" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить версию" }));
    await waitFor(() =>
      expect(createAuditVersion).toHaveBeenCalledWith("s1", "Для банка"));
  });
});
