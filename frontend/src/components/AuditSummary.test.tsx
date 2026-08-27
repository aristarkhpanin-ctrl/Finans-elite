// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuditHeadMetric, AuditSummary as Summary } from "../api/audit";
import { AuditSummary } from "./AuditSummary";

/**
 * Сводка дела. Проверяются решения методики, которые легко потерять при следующей
 * правке экрана: вердикт неотделим от охвата, дисконта к цене здесь нет, «не
 * считается» показано прочерком, а пробелы перечислены.
 */

afterEach(cleanup);

function metric(over: Partial<AuditHeadMetric> = {}): AuditHeadMetric {
  return { key: "leverage", label: "Долг / EBIT", value: "2.3636", unit: "ratio",
           note: "норма до 2.5×", tone: "ok", text: "", ...over };
}

function summary(over: Partial<Summary> = {}): Summary {
  return {
    state: "ready", verdict: "ok", headline: "Критических отклонений не выявлено",
    detail: "Красных флагов не найдено. Охват проверки — 61%.", coverage: "0.61",
    open_procedures: 11, metrics: [metric()], risk_flags: 0, warning_flags: 0,
    priced_total: "0", unpriced: 0, input_errors: 0,
    not_computed: ["Оценка сделки (DCF, мультипликаторы) — запрошенной цены в модели нет."],
    ...over,
  };
}

function show(over: Partial<Summary> = {}, on: Record<string, () => void> = {}) {
  render(<AuditSummary summary={summary(over)}
                       onInput={on.onInput ?? (() => {})}
                       onFlags={on.onFlags ?? (() => {})}
                       onProcedures={on.onProcedures ?? (() => {})}
                       onOpinion={on.onOpinion ?? (() => {})} />);
}

describe("Сводка дела", () => {
  it("пустое дело ведёт к вводу, а не показывает зелёный вердикт", () => {
    // «Зелёного по умолчанию» не бывает: без отчётности вердикта не существует.
    show({ state: "empty", headline: "Отчётность ещё не введена",
           detail: "Введите баланс и отчёт о финансовых результатах." });
    expect(screen.getByText("Отчётность ещё не введена")).toBeTruthy();
    expect(screen.getByText("Перейти к вводу отчётности")).toBeTruthy();
    expect(screen.queryByText("Вердикт")).toBeNull();
  });

  it("охват стоит внутри карточки вердикта, а не отдельным блоком", () => {
    // Разнести их — значит позволить прочитать вердикт без охвата.
    show();
    const card = screen.getByText("Вердикт").closest(".verdict")!;
    expect(card.textContent).toContain("Критических отклонений не выявлено");
    expect(card.textContent).toContain("61%");
    expect(card.textContent).toContain("11 незакрытых процедур");
  });

  it("без чек-листа охват не выдумывается", () => {
    show({ coverage: null, open_procedures: 0 });
    expect(screen.getByText("—")).toBeTruthy();
    expect(screen.queryByText(/незакрытых процедур/)).toBeNull();
  });

  it("дисконта к цене на экране нет, и сказано почему", () => {
    // Ровно здесь макет показывает «Дисконт к цене 18%». Число, выведенное из
    // ничего, унесли бы в переговоры.
    show({ priced_total: "140", unpriced: 2 });
    // Ни подписи макета, ни справедливой стоимости — ни как показателя, ни как числа.
    expect(screen.queryByText("Дисконт к цене")).toBeNull();
    expect(screen.queryByText(/Справедлив/)).toBeNull();
    const labels = [...document.querySelectorAll(".sum-metric .mini-label")]
      .map((e) => e.textContent ?? "");
    expect(labels.some((l) => /цен|дисконт/i.test(l))).toBe(false);
    // Единственное упоминание дисконта — объяснение, почему его здесь нет.
    const note = screen.getByText(/Дисконт считается от запрошенной цены/);
    expect(note.textContent).toContain("не скидка к цене");
  });

  it("оценённое влияние без единой оценки — «не определено», а не «0 ₽»", () => {
    // Ноль читался бы как «риски ничего не стоят», а их просто нечем измерить.
    show({ risk_flags: 1, priced_total: "0", unpriced: 1 });
    expect(screen.getByText("не определено")).toBeTruthy();
  });

  it("оценённое влияние показано суммой, когда она есть", () => {
    show({ priced_total: "140", unpriced: 0 });
    expect(screen.getByText(/140/)).toBeTruthy();
  });

  it("несчитаемая величина показана прочерком, а не нулём", () => {
    // «Не считается» и «равно нулю» — разные факты.
    show({ metrics: [metric({ value: null, tone: "neutral",
                              note: "показатель прибыли не положителен" })] });
    const card = screen.getByText("Долг / EBIT").closest(".sum-metric")!;
    expect(card.textContent).toContain("—");
    expect(card.textContent).not.toContain("0×");
  });

  it("кратность подписана как кратность, а не как деньги", () => {
    show();
    expect(screen.getByText("2,36×")).toBeTruthy();
  });

  it("буква качества прибыли выводится как буква", () => {
    show({ metrics: [metric({ key: "grade", label: "Качество прибыли", unit: "grade",
                              value: null, text: "B", tone: "warn" })] });
    expect(screen.getByText("B")).toBeTruthy();
  });

  it("пробелы перечислены, а не оставлены молчанием", () => {
    show();
    expect(screen.getByText(/принимает его отсутствие/)).toBeTruthy();
    expect(screen.getByText(/Оценка сделки/)).toBeTruthy();
  });

  it("вердикт «данные противоречивы» подан отдельным состоянием", () => {
    show({ verdict: "unreliable", headline: "Вердикт по этим данным не выносится",
           input_errors: 1 });
    const card = screen.getByText("Вердикт").closest(".verdict")!;
    expect(card.className).toContain("verdict--unreliable");
    expect(screen.getByText("Вердикт по этим данным не выносится")).toBeTruthy();
  });

  it("переходы ведут в те разделы, о которых говорит сводка", () => {
    const onFlags = vi.fn(), onProcedures = vi.fn(), onOpinion = vi.fn();
    show({}, { onFlags, onProcedures, onOpinion });
    fireEvent.click(screen.getByText("Открыть реестр флагов"));
    fireEvent.click(screen.getByText(/незакрытых процедур/));
    fireEvent.click(screen.getByText("Открыть заключение"));
    expect(onFlags).toHaveBeenCalled();
    expect(onProcedures).toHaveBeenCalled();
    expect(onOpinion).toHaveBeenCalled();
  });
});
