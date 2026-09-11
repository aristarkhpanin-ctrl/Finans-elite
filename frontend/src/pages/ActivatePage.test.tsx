// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AxiosError } from "axios";
import { ActivatePage } from "./ActivatePage";

/**
 * Активация приглашения. Проверяется то, что раньше было дырой в продукте: до этого
 * приглашённый не мог войти вовсе, а интерфейс сообщал ему, что письмо отправлено.
 */

const activateInvite = vi.fn();
vi.mock("../api/auth", async (orig) => ({
  ...(await orig<typeof import("../api/auth")>()),
  activateInvite: (...a: unknown[]) => activateInvite(...a),
}));

const setToken = vi.fn();
vi.mock("../api/client", async (orig) => ({
  ...(await orig<typeof import("../api/client")>()),
  setToken: (...a: unknown[]) => setToken(...a),
}));

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  // переход после успеха — через window.location.assign; в jsdom его надо подменить
  Object.defineProperty(window, "location", {
    value: { ...window.location, origin: "https://app.test", assign: vi.fn() },
    writable: true,
  });
});

/** Ошибка в том виде, в каком её отдаёт клиент: httpStatus читает признак axios. */
function httpError(status: number): AxiosError {
  const e = new AxiosError("fail");
  e.response = { status, data: {}, statusText: "", headers: {},
                 config: e.config ?? ({} as never) };
  return e;
}

function show(search = "?token=abc") {
  render(
    <MemoryRouter initialEntries={["/activate" + search]}>
      <Routes>
        <Route path="/activate" element={<ActivatePage />} />
        <Route path="/login" element={<div>Экран входа</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const fill = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe("Активация приглашения", () => {
  it("без кода в ссылке объясняет, что делать", () => {
    // Пустая форма «задайте пароль» без токена привела бы к отказу после ввода.
    show("");
    expect(screen.getByText("Ссылка неполная")).toBeTruthy();
    expect(screen.queryByLabelText("Пароль")).toBeNull();
  });

  it("пароль заводится и человек оказывается внутри", async () => {
    activateInvite.mockResolvedValue({ access_token: "T", token_type: "bearer" });
    show();
    fill("Как вас зовут", "Аналитик");
    fill("Пароль", "newpass123");
    fill("Пароль ещё раз", "newpass123");
    fireEvent.click(screen.getByText("Задать пароль и войти"));

    await waitFor(() => expect(activateInvite).toHaveBeenCalledWith({
      token: "abc", password: "newpass123", full_name: "Аналитик",
    }));
    expect(setToken).toHaveBeenCalledWith("T");
  });

  it("несовпадающие пароли не отправляются", () => {
    show();
    fill("Пароль", "newpass123");
    fill("Пароль ещё раз", "другое123");
    expect(screen.getByText(/Пароли не совпадают/)).toBeTruthy();
    fireEvent.click(screen.getByText("Задать пароль и войти"));
    expect(activateInvite).not.toHaveBeenCalled();
  });

  it("короткий пароль не отправляется", () => {
    // То же правило, что на бэкенде: 8 символов. Форма не должна звать на отказ.
    show();
    fill("Пароль", "1234");
    fill("Пароль ещё раз", "1234");
    fireEvent.click(screen.getByText("Задать пароль и войти"));
    expect(activateInvite).not.toHaveBeenCalled();
  });

  it("использованное приглашение объясняется, а не показывается общей ошибкой", async () => {
    activateInvite.mockRejectedValue(httpError(409));
    show();
    fill("Пароль", "newpass123");
    fill("Пароль ещё раз", "newpass123");
    fireEvent.click(screen.getByText("Задать пароль и войти"));
    await waitFor(() => expect(screen.getByRole("alert").textContent)
      .toContain("уже активировано"));
  });

  it("протухшая ссылка говорит, что делать дальше", async () => {
    activateInvite.mockRejectedValue(httpError(400));
    show();
    fill("Пароль", "newpass123");
    fill("Пароль ещё раз", "newpass123");
    fireEvent.click(screen.getByText("Задать пароль и войти"));
    await waitFor(() => expect(screen.getByRole("alert").textContent)
      .toContain("пригласить вас заново"));
  });
});
