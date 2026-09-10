// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditLogEntry } from "../../api/org";
import { AuditLogTab } from "./AuditLogTab";

/**
 * Журнал действий: проверяются решения, а не вёрстка. Действие удалённого участника
 * остаётся подписанным, коды переводятся на человеческий, а вынос данных наружу виден
 * отдельно от обычной правки.
 */

const getAuditLog = vi.fn();
const downloadAuditLogCsv = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getAuditLog: (...a: unknown[]) => getAuditLog(...a),
  downloadAuditLogCsv: (...a: unknown[]) => downloadAuditLogCsv(...a),
}));

const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

function entry(over: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: "e1", actor_email: "owner@e.ru", action: "case.create",
    entity_type: "case", entity_id: "c1", entity_name: "ООО «Цель»",
    details: "", created_at: "2026-08-27T09:30:00Z", ...over,
  } as AuditLogEntry;
}

async function show(entries: AuditLogEntry[], total = entries.length,
                    facets: { actors?: string[]; actions?: string[] } = {}) {
  getAuditLog.mockResolvedValue({
    entries, total,
    actors: facets.actors ?? ["owner@e.ru"],
    actions: facets.actions ?? ["case.create"],
  });
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

  /** Отбор и выгрузка (A2): журнал без них есть, а ответа из него не достать. */

  it("оба продукта переведены на человеческий, а не только «Аудит»", async () => {
    await show([entry({ action: "project.finalize", entity_name: "Завод" }),
                entry({ id: "e2", action: "auth.login_failed", entity_name: "" })]);
    expect(screen.getByText("План финализирован")).toBeTruthy();
    expect(screen.getByText("Неудачная попытка входа")).toBeTruthy();
  });

  it("отбор уходит на сервер, а не фильтрует показанное", async () => {
    // Фильтровать уже загруженные 200 строк значило бы искать в горсти, а не в журнале.
    await show([entry()]);
    fireEvent.change(screen.getByLabelText("Поиск по журналу"),
                     { target: { value: "Завод" } });
    await waitFor(() => expect(getAuditLog)
      .toHaveBeenLastCalledWith("o1", expect.objectContaining({ q: "Завод" })));
  });

  it("предлагаются только встречавшиеся участники и действия", async () => {
    await show([entry()], 1, { actors: ["a@e.ru", "b@e.ru"], actions: ["project.delete"] });
    // Не весь каталог кодов и не список текущих участников: удалённый сотрудник из
    // участников исчез, а из журнала — нет.
    const actions = screen.getByLabelText("Действие") as HTMLSelectElement;
    const options = [...actions.options].map((o) => o.textContent);
    expect(options).toEqual(["Все действия", "Удалён проект"]);
    const actors = screen.getByLabelText("Участник") as HTMLSelectElement;
    expect([...actors.options].map((o) => o.value)).toEqual(["", "a@e.ru", "b@e.ru"]);
  });

  it("выгрузка идёт под тем же отбором, что на экране", async () => {
    await show([entry()]);
    fireEvent.change(screen.getByLabelText("Поиск по журналу"),
                     { target: { value: "Завод" } });
    fireEvent.click(screen.getByText("CSV"));
    await waitFor(() => expect(downloadAuditLogCsv)
      .toHaveBeenCalledWith("o1", expect.objectContaining({ q: "Завод" })));
  });

  it("пустой результат отбора не выдаётся за пустой журнал", async () => {
    getAuditLog.mockResolvedValue({ entries: [], total: 0, actors: [], actions: [] });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><AuditLogTab orgId="o1" /></QueryClientProvider>);
    await screen.findByText("Журнал пуст");
    fireEvent.change(screen.getByLabelText("Поиск по журналу"),
                     { target: { value: "чего-то нет" } });
    await screen.findByText("По отбору ничего не найдено");
  });

  it("сброс возвращает журнал целиком", async () => {
    await show([entry()]);
    fireEvent.change(screen.getByLabelText("Поиск по журналу"), { target: { value: "х" } });
    await waitFor(() => expect(getAuditLog)
      .toHaveBeenLastCalledWith("o1", expect.objectContaining({ q: "х" })));
    fireEvent.click(screen.getByText("Сбросить"));
    await waitFor(() => expect(getAuditLog).toHaveBeenLastCalledWith("o1", {}));
  });
});
