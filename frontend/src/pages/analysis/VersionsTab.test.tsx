// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { VersionDiff, VersionSummary } from "../../api/versions";
import { VersionsTab } from "./VersionsTab";

const versions: VersionSummary[] = [
  { id: "v1", label: "Базовая", created_at: "2026-07-01T10:00:00Z",
    npv: "1000000", irr_annual: "0.2", engine_version: "0.9.29" },
];

const diff: VersionDiff = {
  base_id: "v1", against: "current",
  model_changes: [
    { path: "header.name", kind: "changed", old: "Старое", new: "Новое" },
    { path: "settings.vat_rate", kind: "added", old: null, new: "0.20" },
  ],
  model_changes_truncated: false,
  metric_changes: [
    { key: "npv", label: "NPV", old: "1000000", new: "1500000" },
    { key: "pi", label: "PI", old: "1.2", new: "1.2" },
  ],
};

vi.mock("../../api/versions", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/versions")>()),
  listVersions: vi.fn(async () => versions),
  diffVersion: vi.fn(async () => diff),
  createVersion: vi.fn(),
  restoreVersion: vi.fn(),
  deleteVersion: vi.fn(),
}));

afterEach(cleanup);

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <VersionsTab projectId="p1" />
    </QueryClientProvider>,
  );
}

describe("VersionsTab", () => {
  it("рендерит список версий с метаданными", async () => {
    renderTab();
    expect(await screen.findByText("Базовая")).toBeTruthy();
    expect(screen.getByText(/IRR/)).toBeTruthy();
  });

  it("раскрывает диф: изменённые показатели и изменения модели", async () => {
    renderTab();
    fireEvent.click(await screen.findByText("Сравнить с текущей"));
    // изменённый показатель показан, неизменный (PI) отфильтрован
    await waitFor(() => expect(screen.getByText("Изменения модели (2)")).toBeTruthy());
    expect(screen.getByText("header.name")).toBeTruthy();
    expect(screen.getByText("settings.vat_rate")).toBeTruthy();
    expect(screen.getByText("NPV")).toBeTruthy();
    expect(screen.queryByText("PI")).toBeNull();          // неизменный показатель скрыт
  });
});
