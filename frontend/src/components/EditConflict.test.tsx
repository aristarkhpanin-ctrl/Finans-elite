// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CONFLICT_FALLBACK, EditConflictModal, useEditConflict } from "./EditConflict";

/**
 * Конфликт одновременной правки (G2).
 *
 * Проверяются обещания экрана: причина сервера показывается дословно (кто и когда
 * сохранил), безопасный выход — одним нажатием, а оба разрушительных — только вторым:
 * модалку, где «перезаписать» стоит рядом с «отменой», однажды нажмут не глядя.
 */

afterEach(cleanup);

const axiosError = (status: number, detail?: string) =>
  Object.assign(new Error("x"), {
    isAxiosError: true,
    response: { status, data: detail === undefined ? {} : { detail } },
  });

describe("useEditConflict", () => {
  it("409 открывает конфликт со словами сервера", () => {
    const { result } = renderHook(() => useEditConflict());
    let caught = false;
    act(() => {
      caught = result.current.catchConflict(axiosError(409, "Проект изменён: он сохранён (a@e.ru)."));
    });
    expect(caught).toBe(true);
    expect(result.current.open).toBe(true);
    expect(result.current.detail).toBe("Проект изменён: он сохранён (a@e.ru).");
  });

  it("другие ошибки конфликтом не считаются — у них свой путь", () => {
    const { result } = renderHook(() => useEditConflict());
    let caught = true;
    act(() => { caught = result.current.catchConflict(axiosError(422, "поле")); });
    expect(caught).toBe(false);
    expect(result.current.open).toBe(false);
  });

  it("без причины — запасной текст, а не пустая модалка", () => {
    const { result } = renderHook(() => useEditConflict());
    act(() => { result.current.catchConflict(axiosError(409)); });
    expect(result.current.detail).toBe(CONFLICT_FALLBACK);
  });
});

describe("EditConflictModal", () => {
  function show(kind: "project" | "case" = "project") {
    const handlers = { onSaveCopy: vi.fn(), onTakeTheirs: vi.fn(), onOverwrite: vi.fn(),
                       onClose: vi.fn() };
    render(<EditConflictModal kind={kind} open detail="Проект изменён: он сохранён (a@e.ru)."
                              {...handlers} />);
    return handlers;
  }

  it("показывает, кто и когда сохранил, — дословно", () => {
    show();
    expect(screen.getByText("Проект изменён: он сохранён (a@e.ru).")).toBeTruthy();
  });

  it("безопасный выход — одним нажатием: ничьи правки не пропадают", () => {
    const h = show();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить мои правки новым проектом" }));
    expect(h.onSaveCopy).toHaveBeenCalledTimes(1);
  });

  it("«открыть их версию» срабатывает только со второго нажатия", () => {
    const h = show();
    fireEvent.click(screen.getByRole("button", { name: "Открыть их версию" }));
    expect(h.onTakeTheirs).not.toHaveBeenCalled();
    expect(screen.getByText(/Нажмите ещё раз: ваши несохранённые правки пропадут/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Точно: открыть их версию" }));
    expect(h.onTakeTheirs).toHaveBeenCalledTimes(1);
  });

  it("«сохранить поверх» срабатывает только со второго нажатия и говорит, чьё пропадёт", () => {
    const h = show();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить мои правки поверх" }));
    expect(h.onOverwrite).not.toHaveBeenCalled();
    expect(screen.getByText(/правки, сохранённые раньше вас, пропадут/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Точно: сохранить мои поверх" }));
    expect(h.onOverwrite).toHaveBeenCalledTimes(1);
  });

  it("первое нажатие одного выхода не взводит другой", () => {
    const h = show();
    fireEvent.click(screen.getByRole("button", { name: "Открыть их версию" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить мои правки поверх" }));
    expect(h.onTakeTheirs).not.toHaveBeenCalled();
    expect(h.onOverwrite).not.toHaveBeenCalled();
  });

  it("у дела свои слова: род другой", () => {
    show("case");
    expect(screen.getByText("Пока вы правили, дело изменили")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Сохранить мои правки новым делом" })).toBeTruthy();
  });
});
