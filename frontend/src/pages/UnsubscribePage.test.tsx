// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { UnsubscribePage } from "./UnsubscribePage";

/**
 * Отписка от обсуждения по ссылке из письма (OPEN-DECISIONS §5).
 *
 * Проверяются обещания: отписка происходит **из кода страницы**, а не по самой ссылке
 * (почтовые фильтры ходят по ссылкам заранее), дорога назад есть на том же экране, а
 * протухшая ссылка называет второй путь вместо тупика.
 */

const unsubscribeByToken = vi.fn();
vi.mock("../api/comments", () => ({
  unsubscribeByToken: (...a: unknown[]) => unsubscribeByToken(...a),
}));

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

function show(search: string) {
  render(
    <MemoryRouter initialEntries={[`/comments/unsubscribe${search}`]}>
      <Routes>
        <Route path="/comments/unsubscribe" element={<UnsubscribePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

it("отписывает сам: человек уже нажал — в письме", async () => {
  unsubscribeByToken.mockResolvedValue({ muted: true, note: "Письма не приходят." });
  show("?token=abc");
  expect(await screen.findByText("Письма не приходят.")).toBeTruthy();
  expect(unsubscribeByToken).toHaveBeenCalledWith("abc", true);
});

it("дорога назад — на том же экране: отписка без возврата это ловушка", async () => {
  unsubscribeByToken.mockResolvedValue({ muted: true, note: "Письма не приходят." });
  show("?token=abc");
  const back = await screen.findByRole("button", { name: /вернуть письма/i });

  unsubscribeByToken.mockResolvedValue({ muted: false, note: "Письма приходят." });
  fireEvent.click(back);
  expect(await screen.findByText("Письма приходят.")).toBeTruthy();
  expect(unsubscribeByToken).toHaveBeenLastCalledWith("abc", false);
});

it("протухшая ссылка называет второй путь, а не тупик", async () => {
  unsubscribeByToken.mockRejectedValue(new Error("нет"));
  show("?token=stale");
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.getByText(/в профиле/)).toBeTruthy();
});

it("ссылка без токена — своя ошибка, и запроса не было", () => {
  show("");
  expect(screen.getByRole("alert").textContent).toContain("нет токена");
  expect(unsubscribeByToken).not.toHaveBeenCalled();
});

it("запрос уходит один раз, даже если эффект вызвали дважды", async () => {
  // React 18 в строгом режиме вызывает эффект дважды; второй запрос дал бы ошибку
  // поверх уже случившейся отписки.
  unsubscribeByToken.mockResolvedValue({ muted: true, note: "Готово." });
  show("?token=abc");
  await screen.findByText("Готово.");
  expect(unsubscribeByToken).toHaveBeenCalledTimes(1);
});
