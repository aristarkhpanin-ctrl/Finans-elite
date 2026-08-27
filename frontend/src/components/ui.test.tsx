// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Field } from "./ui";

/**
 * Доступность поля ввода. Оба инварианта — из разряда тех, что не видно глазом и
 * ловится только тестом: подпись либо связана с полем, либо нет, и разница заметна
 * только скринридеру.
 */

afterEach(cleanup);

describe("Поле ввода", () => {
  it("подпись связана с полем без явного id", () => {
    // id почти нигде не передают, поэтому «по умолчанию не связано» означало бы
    // «не связано никогда»: скринридер читал бы поле как безымянное.
    render(<Field label="Название" defaultValue="" />);
    const input = screen.getByLabelText("Название");
    expect(input.tagName).toBe("INPUT");
  });

  it("переданный id уважается", () => {
    render(<Field label="Своё" id="mine" defaultValue="" />);
    expect(screen.getByLabelText("Своё").getAttribute("id")).toBe("mine");
  });

  it("подсказка — описание поля, а не часть его имени", () => {
    // Внутри <label> текст подсказки попадал в имя, и поле звалось
    // «Пароль Не короче 8 символов» — это описание, а не название.
    render(<Field label="Пароль" hint="Не короче 8 символов." defaultValue="" />);
    const input = screen.getByLabelText("Пароль");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy, "подсказка не связана с полем").toBeTruthy();
    expect(document.getElementById(describedBy!)?.getAttribute("aria-label"))
      .toBe("Не короче 8 символов.");
  });

  it("два поля на экране не делят один id", () => {
    render(<><Field label="Первое" defaultValue="" /><Field label="Второе" defaultValue="" /></>);
    const a = screen.getByLabelText("Первое").getAttribute("id");
    const b = screen.getByLabelText("Второе").getAttribute("id");
    expect(a).toBeTruthy();
    expect(a).not.toBe(b);
  });
});
