// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { AuditBenchmarkView } from "../api/audit";
import { AuditBenchmark } from "./AuditBenchmark";

/**
 * Сравнение с ориентиром организации (Прил. Ф).
 *
 * Ценность блока держится на одном: читатель обязан видеть, **чьё** это число. Ориентир
 * без автора и даты неотличим от рыночной медианы, которой у платформы нет, — поэтому
 * оговорка и подпись проверяются наравне с самим сравнением, а отказ обязан называть
 * причину вместо нулей.
 */

afterEach(cleanup);

function view(over: Partial<AuditBenchmarkView> = {}): AuditBenchmarkView {
  return {
    available: true, blockers: [], industry: "Перевозки", metric: "ev_ebitda",
    metric_label: "EV / EBITDA", benchmark: "5.0", case_multiple: "4.4",
    deviation: "-0.12", source: "медиана по 3 сделкам фонда", updated_at: "2026-09-01",
    caveats: ["Это ориентир вашей организации, а не рынок: платформа не собирает "
              + "статистику сделок."],
    not_computed: ["Подбор сделок-аналогов — базы сделок у платформы нет."],
    ...over,
  };
}

describe("Сравнение с ориентиром организации", () => {
  it("число подписано автором и датой", () => {
    render(<AuditBenchmark view={view()} />);
    expect(screen.getByText(/медиана по 3 сделкам фонда/).textContent)
      .toContain("01.09.2026");
  });

  it("оговорка «это не рынок» показывается и при совпадении с ориентиром", () => {
    // Оговорка — условие чтения блока, а не реакция на отклонение.
    render(<AuditBenchmark view={view({ case_multiple: "5.0", deviation: "0" })} />);
    expect(screen.getByText(/а не рынок/)).toBeTruthy();
  });

  it("отклонение показано долей и стороной", () => {
    render(<AuditBenchmark view={view()} />);
    expect(screen.getByText("−12%")).toBeTruthy();
    expect(screen.getByText("оценка дела ниже ориентира")).toBeTruthy();
  });

  it("нулевой ориентир не даёт доли — прочерк, а не бесконечность", () => {
    render(<AuditBenchmark view={view({ benchmark: "0", deviation: null })} />);
    expect(screen.getByText("доли нет — ориентир равен нулю")).toBeTruthy();
  });

  it("несостоявшееся сравнение называет причину, а не показывает нули", () => {
    render(<AuditBenchmark view={view({
      available: false, benchmark: null, case_multiple: null, deviation: null,
      blockers: ["Ориентиры организации не заведены: сравнивать не с чем."],
    })} />);
    expect(screen.getByText("Сравнение не посчитано")).toBeTruthy();
    expect(screen.getByText(/не заведены/)).toBeTruthy();
    expect(screen.queryByText("0×")).toBeNull();
  });

  it("отказ платформы от рыночных медиан остаётся названным", () => {
    render(<AuditBenchmark view={view()} />);
    expect(screen.getByText(/базы сделок у платформы нет/)).toBeTruthy();
  });

  it("ориентир без источника не притворяется подписанным", () => {
    render(<AuditBenchmark view={view({ source: "", updated_at: null })} />);
    expect(screen.getByText("источник не указан")).toBeTruthy();
  });
});
