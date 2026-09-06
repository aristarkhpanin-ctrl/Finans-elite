import { describe, expect, it } from "vitest";
import type { MetricsOut, ValuationOut } from "./api/calc";
import { efficiencyCards, foreignCards, valuationCards } from "./metricCards";

/**
 * Проверяется **вердикт**, а не оформление: тон карточки — это утверждение о проекте,
 * которое пользователь читает как приговор. Перепутанный знак покрасил бы убыточный
 * проект зелёным, и никакая проверка ядра этого не поймала бы: числа-то верные.
 */

const metrics = (over: Partial<MetricsOut> = {}): MetricsOut => ({
  npv: "1000000",
  irr_annual: "0.25",
  mirr_annual: "0.22",
  arr_annual: "0.18",
  pi: "1.4",
  pb_months: 18,
  dpb_months: 24,
  pv_investments: "500000",
  peak_financing_need: "800000",
  ...over,
} as MetricsOut);

const card = (m: MetricsOut, label: string, rate?: string | null) =>
  efficiencyCards(m, rate).find((c) => c.label === label)!;

describe("NPV — знак решает вердикт", () => {
  it("положительный создаёт стоимость", () => {
    const c = card(metrics({ npv: "1000000" }), "NPV");
    expect(c.tone).toBe("good");
    expect(c.sub).toBe("Создаёт стоимость");
  });

  it("отрицательный разрушает стоимость", () => {
    const c = card(metrics({ npv: "-1" }), "NPV");
    expect(c.tone).toBe("bad");
    expect(c.sub).toBe("Разрушает стоимость");
  });

  it("ровно ноль — «на грани», а не «хорошо»", () => {
    const c = card(metrics({ npv: "0" }), "NPV");
    expect(c.tone).toBe("warn");
    expect(c.sub).toBe("На грани");
  });
});

describe("Доходность против ставки", () => {
  it("выше ставки — зелёный, ниже — красный", () => {
    expect(card(metrics({ irr_annual: "0.25" }), "IRR", "0.15").tone).toBe("good");
    expect(card(metrics({ irr_annual: "0.10" }), "IRR", "0.15").tone).toBe("bad");
  });

  it("ровно на ставке считается достаточным", () => {
    const c = card(metrics({ irr_annual: "0.15" }), "IRR", "0.15");
    expect(c.tone).toBe("good");
    expect(c.sub).toContain("Выше ставки");
  });

  it("без IRR — «не определена» и нейтральный тон", () => {
    const c = card(metrics({ irr_annual: null }), "IRR", "0.15");
    expect(c.value).toBe("—");
    expect(c.sub).toBe("Не определена");
    expect(c.tone).toBe("");
  });

  it("ставка ещё не известна — тон нейтральный, а не зелёный", () => {
    // модель проекта не загрузилась: сравнивать не с чем, и «хорошо» было бы выдумкой,
    // которая мигнула бы зелёным и через мгновение покраснела
    const c = card(metrics({ irr_annual: "0.25" }), "IRR", undefined);
    expect(c.tone).toBe("");
    expect(c.sub).toBe("Годовая доходность");
  });

  it("MIRR судится по тому же правилу", () => {
    expect(card(metrics({ mirr_annual: "0.20" }), "MIRR", "0.15").tone).toBe("good");
    expect(card(metrics({ mirr_annual: "0.10" }), "MIRR", "0.15").tone).toBe("bad");
    expect(card(metrics({ mirr_annual: null }), "MIRR", "0.15").tone).toBe("");
  });
});

describe("PI — граница на единице", () => {
  it("единица уже эффективна, ниже — нет", () => {
    expect(card(metrics({ pi: "1" }), "PI").tone).toBe("good");
    expect(card(metrics({ pi: "0.99" }), "PI").tone).toBe("bad");
  });

  it("ноль — это значение, а не «нет данных»", () => {
    const c = card(metrics({ pi: "0" }), "PI");
    expect(c.value).not.toBe("—");
    expect(c.tone).toBe("bad");
  });

  it("отсутствующий PI не судится", () => {
    const c = card(metrics({ pi: null }), "PI");
    expect(c.value).toBe("—");
    expect(c.tone).toBe("");
  });
});

describe("Окупаемость", () => {
  it("не окупается по дисконтированному, но окупается по простому — «внимание»", () => {
    // деньги возвращаются, но их стоимость во времени не покрыта: это не «плохо» и не
    // «хорошо», и красить в один из двух цветов было бы упрощением
    const c = card(metrics({ pb_months: 20, dpb_months: null }), "Дисконт. окупаемость");
    expect(c.tone).toBe("warn");
  });

  it("не окупается вовсе — красный", () => {
    const c = card(metrics({ pb_months: null, dpb_months: null }), "Дисконт. окупаемость");
    expect(c.tone).toBe("bad");
    expect(card(metrics({ pb_months: null }), "Срок окупаемости").value).toBe("> горизонта");
  });
});

describe("Оценка стоимости — без вердиктов", () => {
  it("несчитанные модели дают прочерк, а не ноль", () => {
    const v = { net_assets: "500000", gordon_value: null, dividend_value: null,
                earnings_multiple_value: null, liquidation_value: null } as ValuationOut;
    const cards = valuationCards(v);
    expect(cards.find((c) => c.label === "Модель Гордона")!.value).toBe("—");
    expect(cards.find((c) => c.label === "Чистые активы")!.value).not.toBe("—");
  });

  it("ноль — это оценка, и она показывается", () => {
    const v = { net_assets: "0", gordon_value: "0", dividend_value: null,
                earnings_multiple_value: null, liquidation_value: null } as ValuationOut;
    expect(valuationCards(v).find((c) => c.label === "Модель Гордона")!.value).not.toBe("—");
  });
});

describe("Вторая валюта", () => {
  it("без блока показателей карточек нет", () => {
    expect(foreignCards(null, "USD", "0.1")).toEqual([]);
  });

  it("код валюты попадает и в значение, и в пояснение", () => {
    const cards = foreignCards(metrics(), "USD", "0.1");
    expect(cards).toHaveLength(6);
    expect(cards[0].value).toContain("USD");
    expect(cards[0].hint).toContain("USD");
  });
});

describe("Набор карточек", () => {
  it("состав и порядок не зависят от данных — сетка не «прыгает»", () => {
    const full = efficiencyCards(metrics()).map((c) => c.label);
    const empty = efficiencyCards(metrics({
      npv: "0", irr_annual: null, mirr_annual: null, arr_annual: null, pi: null,
      pb_months: null, dpb_months: null, pv_investments: null, peak_financing_need: null,
    })).map((c) => c.label);
    expect(empty).toEqual(full);
    expect(full).toHaveLength(8);
  });
});
