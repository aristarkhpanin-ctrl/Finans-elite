// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuditComparison, AuditCompareRow } from "../api/audit";
import { AuditComparePage } from "./AuditComparePage";

/**
 * Сравнение дел. Проверяются решения методики, которые легко потерять при следующей
 * правке экрана: победитель показывается только там, где «лучше» определено, счёт побед
 * подан как счёт (а не балл), оговорки сопоставимости видны, а дело без отчётности
 * нельзя выбрать — с объяснением, а не молча.
 */

const listMock = vi.fn();
const compareMock = vi.fn();

vi.mock("../api/audit", async (orig) => ({
  ...(await orig<typeof import("../api/audit")>()),
  listAuditSubjects: () => listMock(),
  compareAuditSubjects: (ids: string[]) => compareMock(ids),
}));

afterEach(() => { cleanup(); listMock.mockReset(); compareMock.mockReset(); });

const subject = (id: string, name: string, n = 2) => ({
  id, name, created_at: "", updated_at: "", n_periods: n, balanced: true,
  industry: "Торговля", light: "ok",
});

function row(over: Partial<AuditCompareRow> = {}): AuditCompareRow {
  return { key: "revenue", label: "Выручка последнего периода", unit: "money",
           direction: "higher", values: ["1980", "2400"], texts: [], winner: 1,
           note: "", ...over };
}

function comparison(over: Partial<AuditComparison> = {}): AuditComparison {
  return {
    cases: [
      { subject_id: "a", name: "Первое", industry: "Торговля", currency: "RUB",
        reporting_standard: "rsbu", last_period: "2024", n_periods: 2,
        verdict: "ok", base_code: "EBITDA" },
      { subject_id: "b", name: "Второе", industry: "Подряд", currency: "RUB",
        reporting_standard: "rsbu", last_period: "2024", n_periods: 2,
        verdict: "warning", base_code: "EBITDA" },
    ],
    rows: [row()], wins: [0, 1], comparable: 1,
    caveats: ["Отрасли различаются: медиана мультипликатора своя в каждой."],
    excluded: [],
    not_computed: ["Рекомендация по сделке — выбор зависит от стратегии покупателя."],
    ...over,
  };
}

function show(subjects = [subject("a", "Первое"), subject("b", "Второе")]) {
  listMock.mockResolvedValue(subjects);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><AuditComparePage /></QueryClientProvider>);
}

async function runCompare(data = comparison()) {
  compareMock.mockResolvedValue(data);
  fireEvent.click(await screen.findByText("Первое"));
  fireEvent.click(screen.getByText("Второе"));
  fireEvent.click(screen.getByText(/^Сравнить/));
  await waitFor(() => expect(compareMock).toHaveBeenCalled());
}

describe("Сравнение дел", () => {
  it("сравнить нельзя, пока не выбраны хотя бы два дела", async () => {
    show();
    await screen.findByText("Первое");                 // дождаться списка дел
    expect((screen.getByText(/^Сравнить/) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Первое"));
    expect((screen.getByText(/^Сравнить/) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Второе"));
    expect((screen.getByText(/^Сравнить \(2\)/) as HTMLButtonElement).disabled).toBe(false);
  });

  it("дело без отчётности выбрать нельзя, и сказано почему", async () => {
    // Молча дизейблить — значит оставить человека гадать.
    show([subject("a", "Первое"), subject("b", "Пустое", 0)]);
    expect(await screen.findByText(/отчётность не введена — сравнивать нечего/))
      .toBeTruthy();
    const box = screen.getByText("Пустое").closest("label")!
      .querySelector("input") as HTMLInputElement;
    expect(box.disabled).toBe(true);
  });

  it("победитель показан и подписью, и подсветкой", async () => {
    show();
    await runCompare();
    const table = document.querySelector(".cmp-table")!;
    const cells = within(table as HTMLElement).getAllByText("Второе");
    expect(cells.length).toBeGreaterThan(0);          // столбец «Кто лучше»
    expect(document.querySelector(".cmp-cell--win")).toBeTruthy();
  });

  it("строка без победителя показывает прочерк и объяснение", async () => {
    // Прочерк здесь — не «ничья», а «сравнивать нечем».
    show();
    await runCompare(comparison({
      rows: [row({ key: "equity_value", label: "Цена за 100% доли", direction: null,
                   winner: null,
                   note: "размер, а не качество сделки — «лучше» здесь не определено" })],
      wins: [0, 0], comparable: 0,
    }));
    expect(await screen.findByText(/размер, а не качество сделки/)).toBeTruthy();
    expect(document.querySelector(".cmp-cell--win")).toBeNull();
  });

  it("счёт побед подан как счёт по сопоставимым строкам, а не как балл", async () => {
    show();
    await runCompare();
    const note = (await screen.findByText(/Сводного балла с весами здесь нет/))
      .closest(".obl-totals__note")!;
    expect(note.textContent).toContain("все они видны построчно");
    // «N из M» — у каждого дела своя карточка счёта.
    expect(screen.getAllByText(/из 1/)).toHaveLength(2);
  });

  it("оговорки сопоставимости выведены отдельным блоком", async () => {
    show();
    await runCompare();
    expect(await screen.findByText("Что сравнимо, а что нет")).toBeTruthy();
    expect(screen.getByText(/Отрасли различаются/)).toBeTruthy();
  });

  it("сказано, чего сравнение не говорит", async () => {
    show();
    await runCompare();
    expect(await screen.findByText("Чего это сравнение не говорит")).toBeTruthy();
    expect(screen.getByText(/Рекомендация по сделке/)).toBeTruthy();
  });

  it("несчитаемое значение показано прочерком, а не нулём", async () => {
    show();
    await runCompare(comparison({
      rows: [row({ key: "multiple", label: "Мультипликатор", unit: "ratio",
                   values: ["4.31", null], winner: null })],
      wins: [0, 0], comparable: 0,
    }));
    const table = await screen.findByText("Мультипликатор");
    const cells = table.closest("tr")!.querySelectorAll("td");
    expect(cells[1].textContent).toBe("4,31×");
    expect(cells[2].textContent).toBe("—");
  });

  it("больше четырёх дел рядом не ставится, и это объяснено", async () => {
    show([subject("a", "Первое"), subject("b", "Второе"), subject("c", "Третье"),
          subject("d", "Четвёртое"), subject("e", "Пятое")]);
    for (const name of ["Первое", "Второе", "Третье", "Четвёртое"]) {
      fireEvent.click(await screen.findByText(name));
    }
    expect(screen.getByText(/Больше 4 дел рядом не помещается/)).toBeTruthy();
    fireEvent.click(screen.getByText("Пятое"));
    expect(screen.getByText(/^Сравнить \(4\)/)).toBeTruthy();   // пятое не добавилось
  });

  it("пустой список дел объявлен, а не показан пустотой", async () => {
    show([]);
    expect(await screen.findByText(/Дел пока нет — сравнивать нечего/)).toBeTruthy();
  });
});
