// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorState, Field, Loading, Modal, SelectField } from "./ui";

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

describe("Поле выбора", () => {
  const opts: [string, string][] = [["year", "Год"], ["quarter", "Квартал"]];

  it("подпись связана с селектом", () => {
    // Подпись рядом с селектом видно глазом, но не скринридеру: без htmlFor он
    // читает «список, Год» — что выбирается, не сказано.
    render(<SelectField label="Периодичность" value="year" options={opts} onChange={() => {}} />);
    expect(screen.getByLabelText("Периодичность").tagName).toBe("SELECT");
  });

  it("подсказка — описание, а не часть имени", () => {
    render(<SelectField label="Основа" value="year" options={opts} hint="Признак, не пересчёт."
                        onChange={() => {}} />);
    const select = screen.getByLabelText("Основа");
    const describedBy = select.getAttribute("aria-describedby");
    expect(describedBy, "подсказка не связана с полем").toBeTruthy();
    expect(document.getElementById(describedBy!)?.getAttribute("aria-label"))
      .toBe("Признак, не пересчёт.");
  });
});

describe("Ошибка и загрузка — карточкой, а не словом в углу (матрица состояний P13, H5)", () => {
  it("ошибка без повтора — всё равно карточка с ролью alert", () => {
    render(<ErrorState text="Не удалось загрузить проект." />);
    const card = screen.getByRole("alert");
    expect(card.className).toBe("error-state");
    expect(card.textContent).toContain("Не удалось загрузить проект.");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("с повтором — кнопка «Повторить»", () => {
    const retry = vi.fn();
    render(<ErrorState text="Не удалось" onRetry={retry} />);
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("загрузка — карточка со статусом", () => {
    render(<Loading />);
    expect(screen.getByRole("status").className).toBe("load-card");
    expect(screen.getByRole("status").textContent).toBe("Загрузка…");
  });
});

/**
 * Модалка и клавиатура (H6). Почти все вызовы передают `onClose` стрелочной функцией —
 * новой на каждой перерисовке владельца, — а владелец перерисовывается на каждое нажатие
 * клавиши в поле модалки. Модалка, перезапускающая по этому поводу свой фокус, забирала
 * его у поля после первой же буквы.
 */
function Owner() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Открыть</button>
      <button type="button">Под затемнением</button>
      <Modal open={open} onClose={() => setOpen(false)} title="Новая организация">
        <label htmlFor="org-name">Название</label>
        <input id="org-name" autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        <button type="button">Создать</button>
      </Modal>
    </>
  );
}

describe("Модалка — фокус", () => {
  it("печать в поле не отнимает у него фокус", () => {
    render(<Owner />);
    const opener = screen.getByRole("button", { name: "Открыть" });
    opener.focus();
    fireEvent.click(opener);
    const input = screen.getByLabelText("Название");
    for (const text of ["О", "ОО", "ООО"]) {
      fireEvent.change(document.activeElement as HTMLInputElement, { target: { value: text } });
    }
    expect(input).toHaveProperty("value", "ООО");
    expect(document.activeElement).toBe(input);
  });

  it("autoFocus поля внутри не перебивается фокусом на саму модалку", () => {
    render(<Owner />);
    fireEvent.click(screen.getByRole("button", { name: "Открыть" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Название"));
  });

  it("Esc закрывает и возвращает фокус на кнопку, которая открыла", () => {
    render(<Owner />);
    const opener = screen.getByRole("button", { name: "Открыть" });
    opener.focus();
    fireEvent.click(opener);
    act(() => { fireEvent.keyDown(document, { key: "Escape" }); });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("Tab не уходит за модалку: с последнего — на первый, Shift+Tab — обратно", () => {
    render(<Owner />);
    fireEvent.click(screen.getByRole("button", { name: "Открыть" }));
    const input = screen.getByLabelText("Название");
    const create = screen.getByRole("button", { name: "Создать" });
    create.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(input);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(create);
  });
});
