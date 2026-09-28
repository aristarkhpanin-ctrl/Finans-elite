// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AuditMonteCarlo,
  AuditRisk as Result,
  AuditTornadoBar,
  RiskAnalysis,
} from "../api/audit";
import { AuditRisk } from "./AuditRisk";

/**
 * Анализ рисков. Проверяются решения методики, которые легко потерять при следующей
 * правке экрана: шаг торнадо виден и объявлен соглашением, прогоны без оценки названы,
 * точность результата ограничена точностью догадки, вероятности нет без цены продавца.
 */

afterEach(cleanup);

function bar(over: Partial<AuditTornadoBar> = {}): AuditTornadoBar {
  return { param: "wacc", label: "Ставка дисконтирования", step: "0.10",
           low_price: "938", high_price: "648", low_delta: "162", high_delta: "-127",
           span: "289", note: "", ...over };
}

function mc(over: Partial<AuditMonteCarlo> = {}): AuditMonteCarlo {
  return {
    iterations: 2000, valued: 2000, unvalued: 0, median: "757", mean: "760",
    p10: "647", p25: "700", p75: "820", p90: "893", minimum: "600", maximum: "950",
    histogram: [{ from: "600", to: "700", count: 400 },
                { from: "700", to: "800", count: 1200 },
                { from: "800", to: "950", count: 400 }],
    below_asking: null, median_drift: "-0.024", ...over,
  };
}

function result(over: Partial<Result> = {}): Result {
  return {
    available: true, blockers: [], base_price: "776", step: "0.10",
    tornado: [bar(), bar({ param: "growth", label: "Рост показателя",
                           low_delta: "-41", high_delta: "42", span: "83" })],
    monte_carlo: mc(), warnings: [],
    not_computed: ["Сценарии с вероятностями — вероятности назначает человек."],
    ...over,
  };
}

function settings(over: Partial<RiskAnalysis> = {}): RiskAnalysis {
  return { tornado_step: "0.10", iterations: 2000, seed: 42, uncertain: [], ...over };
}

function show(over: Partial<Result> = {}, opts: {
  settings?: Partial<RiskAnalysis>; onChange?: (n: RiskAnalysis) => void;
} = {}) {
  render(<AuditRisk result={result(over)} settings={settings(opts.settings)}
                    onChange={opts.onChange ?? (() => {})} />);
}

describe("Анализ рисков", () => {
  it("без оценки анализировать нечего, и причина названа", () => {
    show({ available: false, blockers: ["Не введена справочная строка «амортизация»."] });
    expect(screen.getByText("Анализировать нечего")).toBeTruthy();
    expect(screen.getByText(/амортизация/)).toBeTruthy();
    expect(screen.queryByText("Что двигает цену сильнее всего")).toBeNull();
  });

  it("шаг подписан у каждого столбца торнадо", () => {
    // Торнадо, скрывающий свой шаг, выдаёт соглашение за измерение.
    show();
    expect(screen.getAllByText("±10%")).toHaveLength(2);
  });

  it("сказано, что порядок столбцов зависит от соглашения о шаге", () => {
    show();
    const foot = screen.getByText(/Порядок столбцов зависит от соглашения о шаге/)
      .closest(".torn__foot")!;
    expect(foot.textContent).toContain("измените шаг ниже");
  });

  it("число красится по знаку, а не по стороне смещения", () => {
    // У ставки дисконтирования снижение поднимает цену: «+162» в красном читалось бы
    // как потеря, хотя это выигрыш.
    show({ tornado: [bar()] });          // low_delta +162, high_delta −127
    const positive = document.querySelector(".torn__pos")!.textContent!;
    const negative = document.querySelector(".torn__neg")!.textContent!;
    expect(positive).toContain("162");
    expect(positive.startsWith("+")).toBe(true);
    expect(negative).toContain("127");
    expect(negative.startsWith("+")).toBe(false);
  });

  it("рядом с числом сказано, какое смещение дало этот эффект", () => {
    show({ tornado: [bar()] });
    expect(screen.getByText("−10%")).toBeTruthy();
    expect(screen.getByText("+10%")).toBeTruthy();
  });

  it("торнадо объявляет, что не показывает взаимодействия параметров", () => {
    show();
    expect(screen.getByText(/взаимодействия параметров торнадо не показывает/))
      .toBeTruthy();
  });

  it("столбец без одной стороны объясняет, почему её нет", () => {
    show({ tornado: [bar({ high_price: null, high_delta: null, span: null,
                           note: "при смещении в одну из сторон оценка не считается" })] });
    expect(screen.getByText(/оценка не считается/)).toBeTruthy();
  });

  it("без неопределённых допущений Монте-Карло не притворяется анализом", () => {
    show({ monte_carlo: null });
    expect(screen.getByText(/выглядел бы анализом/)).toBeTruthy();
  });

  it("точность результата объявлена ограниченной точностью догадки", () => {
    // Не сноска, а условие чтения всего блока.
    show();
    const note = screen.getByText(/ровно настолько хороши/).closest(".field-note")!;
    expect(note.textContent).toContain("их придумал человек");
  });

  it("прогоны без оценки названы, а не спрятаны", () => {
    show({ monte_carlo: mc({ valued: 1800, unvalued: 200 }) });
    expect(screen.getByText("200")).toBeTruthy();
    expect(screen.getByText(/нулём они не заменены/)).toBeTruthy();
  });

  it("когда все прогоны дали оценку, так и сказано", () => {
    show();
    expect(screen.getByText(/во всех прогонах стоимость существует/)).toBeTruthy();
  });

  it("вероятности нет без цены продавца", () => {
    show();
    expect(screen.getByText(/вероятности не существует/)).toBeTruthy();
  });

  it("вероятность появляется с ценой продавца", () => {
    show({ monte_carlo: mc({ below_asking: "0.78" }) });
    expect(screen.getByText("78%")).toBeTruthy();
    expect(screen.getByText(/доля прогонов из 2000/)).toBeTruthy();
  });

  it("медиана показана рядом с базой и расхождением", () => {
    show();
    const card = screen.getByText("Медиана").closest(".sum-metric")!;
    expect(card.textContent).toContain("расхождение");
    expect(card.textContent).toContain("-2,4%");
  });

  it("оговорки анализа выводятся, а не проглатываются", () => {
    show({ warnings: ["Медиана прогонов расходится с базовой оценкой на 15%."] });
    expect(screen.getByText(/расходится с базовой оценкой/)).toBeTruthy();
  });

  it("зерно объяснено как условие воспроизводимости, а не техническая деталь", () => {
    show();
    expect(screen.getByText(/при том же зерне числа те же/)).toBeTruthy();
  });

  it("распределение задаётся для коэффициента, и это сказано", () => {
    // Иначе человек введёт «0.2», думая про ставку, и получит множитель 0.2.
    show();
    const hint = screen.getByText("коэффициента").closest(".page-sub")!;
    expect(hint.textContent).toContain("не для самого значения");
    expect(hint.textContent).toContain("множитель к базе");
  });

  it("поля распределения меняются вместе с его видом", () => {
    const onChange = vi.fn();
    show({}, { settings: { uncertain: [{ param: "wacc",
                                         distribution: { kind: "uniform", low: "0.9",
                                                         high: "1.1", mean: null,
                                                         std: null, mode: null } }] },
               onChange });
    expect(screen.getByLabelText("Допущение 1: от")).toBeTruthy();
    expect(screen.queryByLabelText("Допущение 1: мода")).toBeNull();
    fireEvent.change(screen.getByLabelText("Допущение 1: распределение"),
                     { target: { value: "triangular" } });
    expect(onChange.mock.calls[0][0].uncertain[0].distribution.kind).toBe("triangular");
  });

  it("шаг торнадо вводится в процентах, а хранится долей", () => {
    const onChange = vi.fn();
    show({}, { onChange });
    fireEvent.change(screen.getByLabelText("Шаг торнадо"), { target: { value: "25" } });
    expect(onChange.mock.calls[0][0].tornado_step).toBe("0.25");
  });

  it("добавление допущения даёт готовое равномерное распределение", () => {
    const onChange = vi.fn();
    show({}, { onChange });
    fireEvent.click(screen.getByText(/Допущение$/));
    expect(onChange.mock.calls[0][0].uncertain[0]).toMatchObject({
      param: "wacc", distribution: { kind: "uniform", low: "0.9", high: "1.1" } });
  });

  it("кнопка удаления называет допущение", () => {
    show({}, { settings: { uncertain: [{ param: "growth",
                                         distribution: { kind: "uniform", low: "0.9",
                                                         high: "1.1", mean: null,
                                                         std: null, mode: null } }] } });
    expect(screen.getByTitle("Удалить допущение «Рост показателя»")).toBeTruthy();
  });

  it("пробелы анализа перечислены", () => {
    show();
    expect(screen.getByText(/Сценарии с вероятностями/)).toBeTruthy();
  });
});
