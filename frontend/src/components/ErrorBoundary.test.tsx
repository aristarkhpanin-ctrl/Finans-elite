// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

const reportClientError = vi.fn();
vi.mock("../errorReport", () => ({ reportClientError: (e: unknown) => reportClientError(e) }));

function Boom(): never {
  throw new Error("boom");
}

afterEach(cleanup); // очищаем DOM между тестами (нет globals:true)

describe("ErrorBoundary", () => {
  it("показывает фолбэк при ошибке рендера ребёнка", () => {
    // React логирует пойманную ошибку — приглушаем шум в выводе теста.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Что-то пошло не так")).toBeTruthy();
    spy.mockRestore();
  });

  it("пойманная ошибка уходит в трекер (он сам решит, включён ли)", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBoundary><Boom /></ErrorBoundary>);
    expect(reportClientError).toHaveBeenCalledWith(expect.objectContaining({ message: "boom" }));
    spy.mockRestore();
  });

  it("рендерит детей, когда ошибок нет", () => {
    render(
      <ErrorBoundary>
        <div>рабочее содержимое</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("рабочее содержимое")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
