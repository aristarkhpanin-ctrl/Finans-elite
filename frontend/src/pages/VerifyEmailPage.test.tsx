// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { VerifyEmailPage } from "./VerifyEmailPage";

/**
 * Подтверждение адреса по ссылке из письма.
 *
 * Проверяется обещание, а не разметка: подтверждение **ничего не запирает**, и
 * протухшая ссылка не должна читаться как потеря доступа — человек, решивший, что
 * лишился учётной записи, пойдёт не в профиль, а в поддержку.
 */

const verifyEmail = vi.fn();
vi.mock("../api/auth", () => ({ verifyEmail: (...a: unknown[]) => verifyEmail(...a) }));

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

function show(search: string) {
  render(
    <MemoryRouter initialEntries={[`/verify-email${search}`]}>
      <Routes><Route path="/verify-email" element={<VerifyEmailPage />} /></Routes>
    </MemoryRouter>,
  );
}

it("подтверждает сам, без второй кнопки: человек уже нажал — в письме", async () => {
  verifyEmail.mockResolvedValue({ verified: true, sent: false,
                                  note: "Адрес подтверждён: уведомления приходят." });
  show("?token=abc");
  expect(await screen.findByText(/Адрес подтверждён/)).toBeTruthy();
  expect(verifyEmail).toHaveBeenCalledWith("abc");
  expect(screen.queryByRole("button", { name: /подтвердить/i })).toBeNull();
});

it("протухшая ссылка не читается как потеря доступа", async () => {
  verifyEmail.mockRejectedValue(new Error("нет"));
  show("?token=stale");
  expect(await screen.findByRole("alert")).toBeTruthy();
  // Главное на этом экране: вход и восстановление пароля от подтверждения не зависят.
  expect(screen.getByText(/не мешает работе/)).toBeTruthy();
  expect(screen.getByText(/запросить в профиле/)).toBeTruthy();
});

it("ссылка без токена — своя ошибка, и запроса не было", () => {
  show("");
  expect(screen.getByRole("alert").textContent).toContain("нет токена");
  expect(verifyEmail).not.toHaveBeenCalled();
});

it("запрос уходит один раз, даже если эффект вызвали дважды", async () => {
  // React 18 в строгом режиме вызывает эффект дважды; второй запрос дал бы ошибку
  // поверх уже случившегося успеха.
  verifyEmail.mockResolvedValue({ verified: true, sent: false, note: "Готово." });
  show("?token=abc");
  await screen.findByText("Готово.");
  expect(verifyEmail).toHaveBeenCalledTimes(1);
});
