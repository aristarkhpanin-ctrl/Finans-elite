// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditLogEntry } from "../../api/org";
import { AuditLogTab } from "./AuditLogTab";

/**
 * Журнал действий: проверяются решения, а не вёрстка. Действие удалённого участника
 * остаётся подписанным, коды переводятся на человеческий, а вынос данных наружу виден
 * отдельно от обычной правки.
 */

const getAuditLog = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getAuditLog: (...a: unknown[]) => getAuditLog(...a),
}));

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

function entry(over: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: "e1", actor_email: "owner@e.ru", action: "case.create",
    entity_type: "case", entity_id: "c1", entity_name: "ООО «Цель»",
    details: "", created_at: "2026-08-27T09:30:00Z", ...over,
  } as AuditLogEntry;
}

async function show(entries: AuditLogEntry[], total = entries.length) {
  getAuditLog.mockResolvedValue({ entries, total });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><AuditLogTab orgId="o1" /></QueryClientProvider>);
  await screen.findByText(entries.length ? /Действия участников/ : "Журнал пуст");
}

describe("Журнал действий", () => {
  it("пустой журнал объясняет, что в нём появится", async () => {
    await show([]);
    expect(screen.getByText("Журнал пуст")).toBeTruthy();
  });

  it("коды действий переведены на человеческий язык", async () => {
    await show([entry({ action: "member.role_change", details: "analyst → editor",
                        entity_name: "an@e.ru" })]);
    expect(screen.getByText(/Изменена роль/)).toBeTruthy();
    expect(screen.getByText(/analyst → editor/)).toBeTruthy();
  });

  it("незнакомый код показывается как есть, а не прячется", async () => {
    // Журнал не вправе умалчивать о действии только потому, что интерфейс о нём
    // ещё не знает: пропущенная строка выглядит как «ничего не было».
    await show([entry({ action: "plan.change" })]);
    expect(screen.getByText(/plan\.change/)).toBeTruthy();
  });

  it("действие удалённого участника остаётся подписанным", async () => {
    await show([entry({ actor_email: "gone@e.ru", action: "case.delete" })]);
    expect(screen.getByText("gone@e.ru")).toBeTruthy();
    expect(screen.getByText(/Дело удалено/)).toBeTruthy();
  });

  it("вынос данных наружу выделен отдельно от обычной правки", async () => {
    const { container } = render(<div />);
    cleanup();
    void container;
    await show([entry({ action: "case.export", details: "DOCX-заключение" }),
                entry({ id: "e2", action: "case.create" })]);
    const rows = document.querySelectorAll(".log-row--attn");
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain("Выгружен документ");
  });

  it("сказано, что показаны не все записи", async () => {
    await show([entry()], 512);
    expect(screen.getByText(/Показаны последние 1 из 512/)).toBeTruthy();
  });

  it("объявлено полное число строк, а не число показанных", async () => {
    // Иначе скринридер прочитает «строка 2 из 2» там, где записей полтысячи.
    await show([entry()], 512);
    expect(screen.getByRole("table").getAttribute("aria-rowcount")).toBe("512");
  });
});
