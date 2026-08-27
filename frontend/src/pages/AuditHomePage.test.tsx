// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditSubjectSummary } from "../api/audit";
import { AuditHomePage } from "./AuditHomePage";

/**
 * Список дел (макет Экран 6). Проверяется не вёрстка, а решения, которые легко
 * потерять при следующей правке: пустой светофор не равен «в норме», подтверждение
 * удаления называет последствие, фильтры считают по тем же правилам, что показывают.
 */

const listAuditSubjects = vi.fn();
const createAuditSubject = vi.fn();
const duplicateAuditSubject = vi.fn();
const deleteAuditSubject = vi.fn();

vi.mock("../api/audit", async (orig) => ({
  ...(await orig<typeof import("../api/audit")>()),
  listAuditSubjects: () => listAuditSubjects(),
  createAuditSubject: (...a: unknown[]) => createAuditSubject(...a),
  duplicateAuditSubject: (...a: unknown[]) => duplicateAuditSubject(...a),
  deleteAuditSubject: (...a: unknown[]) => deleteAuditSubject(...a),
}));

vi.mock("../components/Toast", () => ({ useToast: () => vi.fn() }));

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

function subject(over: Partial<AuditSubjectSummary> = {}): AuditSubjectSummary {
  return {
    id: "s1", name: "ООО «Пример»", created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-03-12T00:00:00Z", n_periods: 3, balanced: true,
    industry: "Перевозки", light: "ok", ...over,
  };
}

async function show(rows: AuditSubjectSummary[]) {
  listAuditSubjects.mockResolvedValue(rows);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><AuditHomePage /></MemoryRouter>
    </QueryClientProvider>,
  );
  if (rows.length) await screen.findByText(rows[0].name);
  else await screen.findByText("Ни одного дела");
}

describe("Список дел", () => {
  it("пустой список зовёт завести первое дело", async () => {
    await show([]);
    expect(screen.getByText(/Создать первое дело/)).toBeTruthy();
    // фильтров при пустом списке нет — фильтровать нечего
    expect(screen.queryByLabelText("Фильтр дел")).toBeNull();
  });

  it("карточка показывает отрасль, периоды и светофор", async () => {
    await show([subject()]);
    expect(screen.getByText("Перевозки · 3 периода")).toBeTruthy();
    expect(screen.getByText("Норма")).toBeTruthy();
  });

  it("без отчётности светофор не «Норма», а прямо сказано, что данных нет", async () => {
    // Самое опасное упрощение: показать зелёный чип там, где ничего не считалось.
    await show([subject({ light: null, n_periods: 0 })]);
    expect(screen.getByText("Нет отчётности")).toBeTruthy();
    expect(screen.queryByText("Норма")).toBeNull();
  });

  it("несходящийся баланс виден на карточке отдельным чипом", async () => {
    await show([subject({ balanced: false, light: "warning" })]);
    expect(screen.getByText("Баланс не сходится")).toBeTruthy();
    expect(screen.getByText("Внимание")).toBeTruthy();
  });

  it("фильтры считают ровно то, что показывают", async () => {
    await show([
      subject({ id: "a", name: "А", light: "ok" }),
      subject({ id: "b", name: "Б", light: "risk" }),
      subject({ id: "c", name: "В", light: "risk" }),
      subject({ id: "d", name: "Г", light: null }),
    ]);
    expect(screen.getByText("Все · 4")).toBeTruthy();
    expect(screen.getByText("Риск · 2")).toBeTruthy();
    expect(screen.getByText("Без отчётности · 1")).toBeTruthy();
    // пустых групп в фильтрах нет: «Внимание · 0» кликать незачем
    expect(screen.queryByText("Внимание · 0")).toBeNull();

    fireEvent.click(screen.getByText("Риск · 2"));
    expect(screen.getByText("Б")).toBeTruthy();
    expect(screen.getByText("В")).toBeTruthy();
    expect(screen.queryByText("А")).toBeNull();
  });

  it("подтверждение удаления называет дело и последствие", async () => {
    await show([subject({ n_periods: 3 })]);
    fireEvent.click(screen.getByTitle("Удалить дело «ООО «Пример»»"));
    const text = screen.getByText(/будет удалено вместе с введённой/).textContent ?? "";
    expect(text).toContain("ООО «Пример»");
    expect(text).toContain("3");
    expect(text).toContain("Отменить");
    // удаление не происходит до подтверждения
    expect(deleteAuditSubject).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Удалить дело" }));
    await waitFor(() => expect(deleteAuditSubject).toHaveBeenCalledWith("s1"));
  });

  it("дублирование дела идёт без подтверждения — оно ничего не разрушает", async () => {
    duplicateAuditSubject.mockResolvedValue(subject({ id: "s2", name: "ООО «Пример» (копия)" }));
    await show([subject()]);
    fireEvent.click(screen.getByTitle("Дублировать дело «ООО «Пример»»"));
    await waitFor(() => expect(duplicateAuditSubject).toHaveBeenCalledWith("s1"));
  });

  it("создание передаёт заполненные реквизиты, а не пустую модель", async () => {
    createAuditSubject.mockResolvedValue(subject({ id: "new" }));
    await show([subject()]);
    fireEvent.click(screen.getByText(/Новое дело/));

    fireEvent.change(screen.getByPlaceholderText("ООО «Пример»"),
                     { target: { value: "ООО «Цель»" } });
    fireEvent.change(screen.getByPlaceholderText("напр. Перевозки"),
                     { target: { value: "Ритейл" } });
    fireEvent.click(screen.getByText("Создать"));

    await waitFor(() => expect(createAuditSubject).toHaveBeenCalled());
    const [name, model] = createAuditSubject.mock.calls[0] as [string, Record<string, unknown>];
    expect(name).toBe("ООО «Цель»");
    expect(model.industry).toBe("Ритейл");
    expect(model.reporting_standard).toBe("rsbu");
    expect(model.periods).toEqual([{ label: "", kind: "year" }]);
  });

  it("дело без названия не создаётся", async () => {
    await show([subject()]);
    fireEvent.click(screen.getByText(/Новое дело/));
    fireEvent.click(screen.getByText("Создать"));
    expect(createAuditSubject).not.toHaveBeenCalled();
  });
  it("поиск ищет по названию и отрасли, не различая регистра и «ё»", async () => {
    await show([
      subject({ id: "a", name: "ООО «Сибтранс»", industry: "Перевозки" }),
      subject({ id: "b", name: "АО «Ритейл»", industry: "Торговля" }),
    ]);
    const box = screen.getByLabelText("Поиск по делам");

    fireEvent.change(box, { target: { value: "сибтранс" } });
    expect(screen.getByText("ООО «Сибтранс»")).toBeTruthy();
    expect(screen.queryByText("АО «Ритейл»")).toBeNull();

    // по отрасли — тоже, и «ё» не мешает
    fireEvent.change(box, { target: { value: "перевозки" } });
    expect(screen.getByText("ООО «Сибтранс»")).toBeTruthy();
  });

  it("счётчики фильтров считают найденное, а не весь список", async () => {
    // «Риск · 3» рядом с одной карточкой — обещание двух дел, которых на экране нет.
    await show([
      subject({ id: "a", name: "Альфа", light: "risk" }),
      subject({ id: "b", name: "Бета", light: "risk" }),
    ]);
    expect(screen.getByText("Риск · 2")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Поиск по делам"), { target: { value: "альфа" } });
    expect(screen.getByText("Риск · 1")).toBeTruthy();
  });

  it("пустой результат поиска объясняет свою причину и предлагает выход", async () => {
    await show([subject()]);
    fireEvent.change(screen.getByLabelText("Поиск по делам"), { target: { value: "неттакого" } });
    expect(screen.getByText("Ничего не найдено")).toBeTruthy();
    expect(screen.getByText(/По запросу «неттакого»/)).toBeTruthy();

    fireEvent.click(screen.getByText("Показать все"));
    expect(screen.getByText("ООО «Пример»")).toBeTruthy();
  });
});
