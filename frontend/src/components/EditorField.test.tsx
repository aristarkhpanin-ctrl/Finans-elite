// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { EField, ESelect } from "./EditorField";

/**
 * Поля редактора модели — подпись связана с полем (H6). До связи ввод звался по
 * заполнителю («0»), а селект был безымянным: `axe-core` в матрице P13 насчитал 21
 * такой селект. Подсказка и ошибка — описание поля, а не часть его имени.
 */

afterEach(cleanup);

const noop = () => undefined;

describe("поле ввода редактора", () => {
  it("подпись — имя поля", () => {
    render(<EField label="Ставка дисконтирования" value="18" onChange={noop} suffix="%" />);
    expect(screen.getByRole("textbox", { name: "Ставка дисконтирования" })).toBeTruthy();
  });

  it("подсказка и ошибка — описание, а не имя", () => {
    render(<EField label="Срок" value="-1" onChange={noop} hint="Месяцев от старта"
                   error="Не меньше нуля" />);
    const input = screen.getByRole("textbox", { name: "Срок" });
    const described = (input.getAttribute("aria-describedby") ?? "").split(" ")
      .map((id) => document.getElementById(id)?.textContent);
    expect(described).toEqual(["Месяцев от старта", "Не меньше нуля"]);
    expect(input.getAttribute("aria-invalid")).toBe("true");
  });

  it("два поля на экране не делят один id", () => {
    render(<><EField label="А" value="" onChange={noop} /><EField label="Б" value="" onChange={noop} /></>);
    expect(screen.getByLabelText("А").id).not.toBe(screen.getByLabelText("Б").id);
  });
});

describe("поле выбора редактора", () => {
  const options: [string, string][] = [["a", "Первый"], ["b", "Второй"]];

  it("у селекта есть имя", () => {
    render(<ESelect label="Группа ОС" value="a" onChange={noop} options={options} />);
    expect(screen.getByRole("combobox", { name: "Группа ОС" })).toBeTruthy();
  });

  it("скрытая подпись — всё равно имя: смысл строки таблицы задаёт колонка", () => {
    render(<ESelect label="Роль: Иван" hideLabel value="a" onChange={noop} options={options} />);
    expect(screen.getByRole("combobox", { name: "Роль: Иван" })).toBeTruthy();
    expect(document.querySelector(".efield__label")).toBeNull();   // на экране её нет
  });
});
