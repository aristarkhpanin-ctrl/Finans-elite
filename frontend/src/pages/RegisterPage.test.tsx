// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Регистрация (L5): согласие на обработку ПД — **отдельная** отметка, снятая по
 * умолчанию; без неё регистрации нет, и причина сказана у самой отметки. Оферта и
 * политика — настоящие ссылки, а не подчёркнутый текст.
 */

const register = vi.fn();
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ register }) }));
vi.mock("../components/CubeHero", () => ({ CubeHero: () => null }));

const { RegisterPage } = await import("./RegisterPage");

function show() {
  render(<MemoryRouter><RegisterPage /></MemoryRouter>);
}

const fill = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

function fillForm() {
  fill("ФИО", "Иван Петров");
  fill("Email", "ivan@example.ru");
  fill("Пароль", "kvartal-plan-77");
  fill("Название организации", "ООО «Ромашка»");
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("Регистрация и согласие на обработку ПД", () => {
  it("отметка согласия снята по умолчанию и ведёт на текст согласия", () => {
    show();
    const box = screen.getByRole("checkbox", { name: /согласие на обработку/ }) as HTMLInputElement;
    expect(box.checked).toBe(false);
    expect(screen.getByRole("link", { name: "согласие на обработку персональных данных" })
      .getAttribute("href")).toBe("/legal/consent");
  });

  it("без согласия форма не уходит и называет причину у отметки", async () => {
    show();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: /Создать аккаунт/ }));
    expect(await screen.findByText(/Без согласия на обработку персональных данных/)).toBeTruthy();
    expect(register).not.toHaveBeenCalled();
  });

  it("с согласием уходит и само согласие", async () => {
    register.mockResolvedValue(undefined);
    show();
    fillForm();
    fireEvent.click(screen.getByRole("checkbox", { name: /согласие на обработку/ }));
    fireEvent.click(screen.getByRole("button", { name: /Создать аккаунт/ }));
    await waitFor(() => expect(register).toHaveBeenCalledWith({
      full_name: "Иван Петров", email: "ivan@example.ru", password: "kvartal-plan-77",
      organization_name: "ООО «Ромашка»", pd_consent: true,
    }));
  });

  it("оферта и политика — ссылки, а не подчёркнутый текст", () => {
    show();
    expect(screen.getByRole("link", { name: "оферты" }).getAttribute("href")).toBe("/legal/offer");
    expect(screen.getByRole("link", { name: "политике обработки персональных данных" })
      .getAttribute("href")).toBe("/legal/privacy");
  });
});
