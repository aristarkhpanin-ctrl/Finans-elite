// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuditValuation as Result, ValuationAssumptions } from "../api/audit";
import { AuditValuation } from "./AuditValuation";

/**
 * Оценка стоимости. Проверяются решения методики, которые легко потерять при следующей
 * правке экрана: «не посчитано» не показывается нулями, дисконта нет без цены продавца,
 * невозможная клетка чувствительности пуста, а мультипликатор объявлен своим.
 */

afterEach(cleanup);

function result(over: Partial<Result> = {}): Result {
  return {
    enabled: true, blockers: [], base_code: "EBITDA", base_ebit: "220",
    wacc: "0.20", terminal_growth: "0.03",
    years: [{ year: 1, ebit: "242", depreciation: "66", capex: "70", nwc_change: "20",
              fcff: "169.6", discount_factor: "0.8333", present_value: "141.3" }],
    pv_forecast: "611.7", terminal_value: "1481", pv_terminal: "595.4",
    enterprise_value: "1207.1", terminal_share: "0.493",
    bridge: [
      { label: "Enterprise Value", amount: "1207.1", kind: "add", note: "" },
      { label: "Долг и займы", amount: "520", kind: "subtract",
        note: "агрегат P_LONG + P_SHORT (включает кредиторку)" },
      { label: "Денежные средства", amount: "130", kind: "add", note: "" },
      { label: "Доля миноритариев", amount: "0", kind: "subtract",
        note: "вводится: в аналитической форме её нет" },
      { label: "Цена за 100% доли", amount: "817.1", kind: "total", note: "" },
    ],
    equity_value: "817.1", implied_multiple: "4.31", asking_price: null, discount: null,
    sensitivity: [["700", "750"], ["800", null]],
    sensitivity_wacc: ["0.16", "0.20"], sensitivity_growth: ["0.01", "0.03"],
    equity_min: "700", equity_max: "800", warnings: [],
    not_computed: ["Сопоставимые сделки — базы сделок-аналогов у платформы нет."],
    ...over,
  };
}

function assumptions(over: Partial<ValuationAssumptions> = {}): ValuationAssumptions {
  return { enabled: true, horizon_years: 3, wacc: "0.20", terminal_growth: "0.03",
           tax_rate: "0.20", growth: ["0.1"], capex: ["70"], nwc_change: ["20"],
           minority_interest: "0", asking_price: null, ...over };
}

function show(over: Partial<Result> = {}, opts: {
  assumptions?: Partial<ValuationAssumptions>; onChange?: (n: ValuationAssumptions) => void;
} = {}) {
  render(<AuditValuation result={result(over)}
                         assumptions={assumptions(opts.assumptions)}
                         onChange={opts.onChange ?? (() => {})} />);
}

describe("Оценка стоимости", () => {
  it("непосчитанная оценка показывает причины, а не нули", () => {
    // «Бизнес стоит 0» и «оценка не посчитана» — разные утверждения.
    show({ blockers: ["Не введена справочная строка «в т.ч. амортизация»."] });
    expect(screen.getByText("Оценка не посчитана")).toBeTruthy();
    expect(screen.getByText(/амортизация/)).toBeTruthy();
    expect(screen.queryByText("Цена за 100% доли")).toBeNull();
    expect(screen.queryByText("Мост EV → цена")).toBeNull();
  });

  it("без цены продавца дисконта нет, и сказано почему", () => {
    show();
    expect(screen.queryByText(/Дисконт к цене \d/)).toBeNull();
    expect(screen.getByText(/Цена продавца не введена/).textContent)
      .toContain("не ноль процентов");
  });

  it("с ценой продавца дисконт появляется", () => {
    show({ asking_price: "1400", discount: "0.4163" });
    expect(screen.getByText(/Дисконт к цене 42%/)).toBeTruthy();
  });

  it("оценка выше запрошенной подана премией, а не отрицательным дисконтом", () => {
    // «Дисконта нет» и «продавец просит меньше нашей оценки» — разные факты.
    show({ asking_price: "700", discount: "-0.1673" });
    expect(screen.getByText(/выше запрошенной на 17%/)).toBeTruthy();
  });

  it("мультипликатор объявлен своим, а не рыночным ориентиром", () => {
    show();
    expect(screen.getByText("4,31×")).toBeTruthy();
    expect(screen.getByText(/не рыночный ориентир/)).toBeTruthy();
  });

  it("база прогноза названа нормализованным EBIT", () => {
    // Ради этого нормализация и делалась — связь обязана быть видна.
    show();
    expect(screen.getByText(/База прогноза/)).toBeTruthy();
    expect(screen.getByText(/нормализованный EBIT последнего периода/)).toBeTruthy();
  });

  it("оговорки оценки выводятся, а не проглатываются", () => {
    show({ warnings: ["Реестр обязательств не заполнен: долг взят агрегатом баланса."] });
    expect(screen.getByText(/Реестр обязательств не заполнен/)).toBeTruthy();
  });

  it("мост показывает знаки слагаемых и пояснение к долгу", () => {
    show();
    const bridge = screen.getByText("Мост EV → цена").closest(".audit-block")!;
    expect(bridge.textContent).toContain("− Долг и займы");
    expect(bridge.textContent).toContain("включает кредиторку");
    expect(bridge.textContent).toContain("Цена за 100% доли");
  });

  it("невозможная клетка чувствительности пуста, а не равна нулю", () => {
    // Ноль читался бы как «здесь бизнес ничего не стоит».
    show();
    const grid = screen.getByText(/По вертикали ставка дисконтирования/)
      .closest(".audit-block")!;
    expect(grid.textContent).toContain("—");
  });

  it("диапазон объявлен чувствительностью, а не сценариями", () => {
    show();
    expect(screen.getByText(/Диапазон по чувствительности/)).toBeTruthy();
    expect(screen.getByText(/отдельных сценариев нет/)).toBeTruthy();
  });

  it("пустая цена продавца уходит наверх как null, а не как ноль", () => {
    const onChange = vi.fn();
    show({}, { assumptions: { asking_price: "1400" }, onChange });
    fireEvent.change(screen.getByLabelText("Запрошенная цена"), { target: { value: "" } });
    expect(onChange.mock.calls[0][0].asking_price).toBeNull();
  });

  it("ставка вводится в процентах, а хранится долей", () => {
    const onChange = vi.fn();
    show({}, { onChange });
    fireEvent.change(screen.getByLabelText("Ставка дисконтирования"),
                     { target: { value: "18,5" } });
    expect(onChange.mock.calls[0][0].wacc).toBe("0.185");
  });

  it("ряды допущений рисуются на весь горизонт", () => {
    show({}, { assumptions: { horizon_years: 3 } });
    expect(screen.getByLabelText("Рост показателя, год 3")).toBeTruthy();
    expect(screen.getByLabelText("Капвложения, год 3")).toBeTruthy();
  });

  it("объяснено, что короткий ряд продлевается, а не обнуляется", () => {
    show();
    expect(screen.getByText(/продлевается последним значением/)).toBeTruthy();
  });

  it("выключенная оценка предлагает её включить", () => {
    show({ enabled: false, blockers: ["Оценка выключена: включите её."] },
         { assumptions: { enabled: false } });
    expect(screen.getByText("Включить оценку")).toBeTruthy();
  });
});
