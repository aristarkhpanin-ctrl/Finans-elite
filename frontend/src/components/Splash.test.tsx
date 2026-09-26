// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Splash } from "./Splash";

// Куб-марка — анимированная сцена на RAF; в тесте она не нужна и только шумит.
vi.mock("./CubeHero", () => ({ CubeHero: () => <div data-testid="cube" /> }));

/**
 * Сплеш рисуется раньше каркаса — и потому единственный экран, у которого нет ни
 * маршрута, ни темы продукта на `<html>`. Проверяется, что он всё равно показывает
 * марку того продукта, в который идёт загрузка.
 */

afterEach(cleanup);
beforeEach(() => localStorage.clear());

const wordmark = () => document.querySelector(".splash__wordmark")!.textContent;

describe("Сплеш", () => {
  it("по умолчанию — бизнес-план", () => {
    render(<Splash progress={40} />);
    expect(wordmark()).toBe("Финанс-Элит");
    expect(document.querySelector(".splash--audit")).toBeNull();
    expect(screen.getByText(/финансовые модели/)).toBeTruthy();
  });

  it("в аудите — своя марка, палитра и статус", () => {
    localStorage.setItem("fe_product", "audit");
    render(<Splash progress={40} />);
    expect(wordmark()).toBe("Финанс-Аудит");
    expect(document.querySelector(".splash--audit")).toBeTruthy();
    expect(screen.getByText(/отчётность по делам/)).toBeTruthy();
  });

  it("явная подпись перекрывает стадию, а процент не выходит за границы", () => {
    render(<Splash progress={140} label="Считаем смету" />);
    expect(screen.getByText("Считаем смету")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
  });
});
