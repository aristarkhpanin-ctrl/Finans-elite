import { describe, expect, it } from "vitest";
import { httpDetail, httpFieldError, httpStatus } from "./client";

/**
 * Разбор отказов сервера.
 *
 * Правка модели уходит **целиком**, поэтому одна непонятая ячейка отклоняет всё. Пока
 * экран говорил «не удалось сохранить», виновную ячейку искали глазами по всей
 * отчётности — а нередко просто теряли введённое. Здесь проверяется, что отказ
 * называет поле и говорит, что с ним не так.
 */

/** Ответ FastAPI на непрошедшую валидацию (422). */
const validation = (loc: unknown[], type: string, input: unknown) => ({
  isAxiosError: true,
  response: { status: 422, data: { detail: [{ type, loc, msg: "…", input }] } },
});

describe("httpFieldError", () => {
  it("называет поле и объясняет, как писать число", () => {
    const msg = httpFieldError(
      validation(["body", "model", "obligations", 0, "amount"], "decimal_parsing", "1.234,56"))!;
    expect(msg).toContain("«1.234,56»");
    expect(msg).toContain("obligations → 1 → amount");   // строки нумеруются с единицы
    expect(msg).toContain("1 200,50");                   // как писать — показано примером
  });

  it("обёртка запроса в пути не показывается", () => {
    // `body` и `model` — конверт API, человек их не заполнял.
    const msg = httpFieldError(validation(["body", "model", "name"], "string_type", 5))!;
    expect(msg).not.toContain("body");
    expect(msg).not.toContain("model");
    expect(msg).toContain("«name»");
  });

  it("нечисловая ошибка не советует писать число", () => {
    const msg = httpFieldError(validation(["body", "name"], "string_type", 5))!;
    expect(msg).toContain("не подходит по формату");
  });

  it("пустой ввод не превращается в пустые кавычки", () => {
    const msg = httpFieldError(validation(["body", "rate"], "decimal_parsing", ""))!;
    expect(msg.startsWith("значение")).toBe(true);
  });

  it("не-422 и сетевая ошибка остаются без разбора", () => {
    expect(httpFieldError({ isAxiosError: true, response: { status: 500, data: {} } }))
      .toBeUndefined();
    expect(httpFieldError(new Error("сеть"))).toBeUndefined();
    // Строковый `detail` — это отказ по существу, его показывают как есть.
    expect(httpFieldError({ isAxiosError: true,
                            response: { status: 409, data: { detail: "Занято" } } }))
      .toBeUndefined();
  });
});

describe("httpDetail и httpStatus", () => {
  it("строковый detail и статус читаются", () => {
    const e = { isAxiosError: true, response: { status: 409, data: { detail: "Занято" } } };
    expect(httpDetail(e)).toBe("Занято");
    expect(httpStatus(e)).toBe(409);
  });

  it("список ошибок валидации за строковый detail не выдаётся", () => {
    // Иначе в тост уехал бы `[object Object]`.
    expect(httpDetail(validation(["body", "x"], "decimal_parsing", "1"))).toBeUndefined();
  });
});
