import { describe, expect, it } from "vitest";
import { allBalanced, balanceGaps, serverGaps } from "./auditBalance";

/**
 * Инвариант «актив = пассив» — единственное, что отделяет отчётность от набора чисел.
 * Клиентская оценка обязана совпадать с серверной хотя бы до копейки: иначе баннер и
 * оговорка анализа говорят об одном и том же противоположное.
 */

const row = (...v: (string | number)[]) => v.map(String);

describe("balanceGaps — разрыв по периодам", () => {
  it("сошедшийся баланс даёт нули", () => {
    const gaps = balanceGaps({
      A_FIXED: row(100), A_CASH: row(100),
      P_EQUITY: row(120), P_SHORT: row(80),
    }, 1);
    expect(gaps).toEqual([0]);
    expect(allBalanced(gaps)).toBe(true);
  });

  it("разрыв считается в копейках со знаком «актив − пассив»", () => {
    const gaps = balanceGaps({ A_CASH: row(100), P_EQUITY: row(90) }, 1);
    expect(gaps).toEqual([1000]);        // 10 ₽ = 1000 коп.
    expect(allBalanced(gaps)).toBe(false);
  });

  it("недостающие строки и периоды считаются нулями, а не ломают расчёт", () => {
    expect(balanceGaps({ A_CASH: row(50) }, 3)).toEqual([5000, 0, 0]);
    expect(balanceGaps({}, 2)).toEqual([0, 0]);
    expect(balanceGaps({ A_CASH: row(1) }, 0)).toEqual([]);
  });

  it("запятая как десятичный разделитель понимается", () => {
    expect(balanceGaps({ A_CASH: ["10,50"], P_EQUITY: ["10,50"] }, 1)).toEqual([0]);
  });
});

describe("Расчёт в копейках убирает шум двоичной плавающей точки", () => {
  it("0,1 + 0,2 против 0,3 — не разрыв", () => {
    // в float 0.1 + 0.2 = 0.30000000000000004; при сравнении «в рублях» это дало бы
    // ненулевой разрыв на пустом месте
    const gaps = balanceGaps({
      A_FIXED: ["0.1"], A_CASH: ["0.2"], P_EQUITY: ["0.3"],
    }, 1);
    expect(gaps).toEqual([0]);
    expect(allBalanced(gaps)).toBe(true);
  });

  it("накопление на длинном ряду статей тоже не даёт хвоста", () => {
    const gaps = balanceGaps({
      A_FIXED: ["1.15"], A_INVENTORY: ["2.35"], A_RECEIVABLE: ["3.45"], A_CASH: ["4.05"],
      P_EQUITY: ["11.00"],
    }, 1);
    expect(gaps).toEqual([0]);
  });
});

describe("Строгость совпадает с сервером", () => {
  it("разрыв в одну копейку — это разрыв", () => {
    const gaps = balanceGaps({ A_CASH: ["100.01"], P_EQUITY: ["100.00"] }, 1);
    expect(gaps).toEqual([1]);
    expect(allBalanced(gaps)).toBe(false);
  });

  it("доли копейки клиент не различает — и потому его ответ предварительный", () => {
    // Сервер (Decimal, ровно ноль) на разрыве 0,003 скажет «не сходится», клиент —
    // «сходится»: в копейках такого разрыва просто нет. Закрывает это не арифметика, а
    // порядок источников: как только модель сохранена, страница показывает вердикт
    // сервера, а предварительная оценка работает лишь пока правки не сохранены.
    const gaps = balanceGaps({ A_CASH: ["100.003"], P_EQUITY: ["100.000"] }, 1);
    expect(gaps).toEqual([0]);
    expect(allBalanced(gaps)).toBe(true);
    expect(allBalanced(serverGaps(["0.01"]))).toBe(false);   // копейка видна обоим
  });
});

describe("serverGaps — вердикт сервера в тех же единицах", () => {
  it("строки-Decimal приводятся к копейкам", () => {
    expect(serverGaps(["0", "-849.00", "0.01"])).toEqual([0, -84900, 1]);
  });

  it("пустой ответ не ломает страницу", () => {
    expect(serverGaps(undefined)).toEqual([]);
    expect(allBalanced(serverGaps([]))).toBe(true);
  });
});
