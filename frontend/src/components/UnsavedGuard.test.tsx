// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { UnsavedLeaveModal, useUnsavedGuard } from "./UnsavedGuard";

/**
 * Страж несохранённого ввода.
 *
 * Цена ошибки здесь — переписывать отчётность заново, поэтому проверяется не вид
 * диалога, а его обязанности: без правок уход мгновенный, с правками — вопрос вместо
 * перехода, «сохранить и выйти» действительно сохраняет **до** перехода, а браузер
 * получает предупреждение о закрытии вкладки ровно пока правки есть.
 */

afterEach(cleanup);

/** Страница-двойник: те же роли, что у редактора проекта и у дела. */
function Page({ dirty, onSave = async () => {}, onGo }: {
  dirty: boolean; onSave?: () => Promise<void>; onGo: () => void;
}) {
  const { tryNav, pending, cancel } = useUnsavedGuard(dirty);
  const [saving, setSaving] = useState(false);
  return (
    <>
      <button onClick={() => tryNav("Дела", onGo)}>← К субъектам</button>
      <UnsavedLeaveModal pending={pending} saving={saving} onCancel={cancel}
                         onSave={async () => { setSaving(true); await onSave(); setSaving(false); }} />
    </>
  );
}

/** Событие закрытия вкладки; отменённое — тот самый вопрос браузера. */
function closeTab(): boolean {
  const e = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(e);
  return e.defaultPrevented;
}

describe("Страж несохранённого ввода", () => {
  it("без правок уход мгновенный, без вопросов", () => {
    const go = vi.fn();
    render(<Page dirty={false} onGo={go} />);
    fireEvent.click(screen.getByText("← К субъектам"));
    expect(go).toHaveBeenCalled();
    expect(screen.queryByText("Несохранённые изменения")).toBeNull();
  });

  it("с правками переход останавливается вопросом", () => {
    const go = vi.fn();
    render(<Page dirty onGo={go} />);
    fireEvent.click(screen.getByText("← К субъектам"));
    expect(go).not.toHaveBeenCalled();
    expect(screen.getByText("Несохранённые изменения")).toBeTruthy();
    expect(screen.getByText(/Дела/)).toBeTruthy();
  });

  it("«сохранить и выйти» сохраняет до перехода, а не после", async () => {
    const order: string[] = [];
    const go = () => order.push("переход");
    render(<Page dirty onGo={go}
                 onSave={async () => { order.push("сохранение"); }} />);
    fireEvent.click(screen.getByText("← К субъектам"));
    fireEvent.click(screen.getByText("Сохранить и выйти"));
    await waitFor(() => expect(order).toEqual(["сохранение", "переход"]));
  });

  it("«выйти без сохранения» уводит, ничего не сохраняя", () => {
    const go = vi.fn();
    const save = vi.fn();
    render(<Page dirty onGo={go} onSave={async () => { save(); }} />);
    fireEvent.click(screen.getByText("← К субъектам"));
    fireEvent.click(screen.getByText("Выйти без сохранения"));
    expect(go).toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
  });

  it("«отмена» оставляет на странице и не теряет введённое", () => {
    const go = vi.fn();
    render(<Page dirty onGo={go} />);
    fireEvent.click(screen.getByText("← К субъектам"));
    fireEvent.click(screen.getByText("Отмена"));
    expect(go).not.toHaveBeenCalled();
    expect(screen.queryByText("Несохранённые изменения")).toBeNull();
  });

  it("закрытие вкладки с правками браузер переспрашивает, без правок — нет", () => {
    const { unmount } = render(<Page dirty onGo={() => {}} />);
    expect(closeTab()).toBe(true);
    unmount();

    render(<Page dirty={false} onGo={() => {}} />);
    expect(closeTab()).toBe(false);
  });

  it("после ухода со страницы обработчик снимается", () => {
    // Иначе список дел спрашивал бы о правках, которых на нём нет.
    const { unmount } = render(<Page dirty onGo={() => {}} />);
    unmount();
    expect(closeTab()).toBe(false);
  });
});
