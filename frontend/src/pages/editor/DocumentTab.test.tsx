// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PlanSection } from "../../api/model";
import { DocumentTab } from "./DocumentTab";

afterEach(cleanup);

const sections: PlanSection[] = [
  { title: "Резюме проекта", text: "Коротко о проекте." },
  { title: "Рынок", text: "Обзор рынка." },
];

describe("DocumentTab", () => {
  it("пустое состояние: приглашение добавить раздел", () => {
    const onChange = vi.fn();
    render(<DocumentTab sections={[]} onChange={onChange} />);
    expect(screen.getByText("Нет разделов")).toBeTruthy();
    fireEvent.click(screen.getByText(/Добавить первый раздел/));
    expect(onChange).toHaveBeenCalledWith([{ title: "", text: "" }]);
  });

  it("рендерит разделы и правит текст", () => {
    const onChange = vi.fn();
    render(<DocumentTab sections={sections} onChange={onChange} />);
    expect(screen.getByDisplayValue("Резюме проекта")).toBeTruthy();
    fireEvent.change(screen.getByDisplayValue("Обзор рынка."), {
      target: { value: "Новый текст." },
    });
    expect(onChange).toHaveBeenCalledWith([sections[0], { title: "Рынок", text: "Новый текст." }]);
  });

  it("двигает раздел вверх", () => {
    const onChange = vi.fn();
    render(<DocumentTab sections={sections} onChange={onChange} />);
    fireEvent.click(screen.getAllByTitle("Выше")[1]);
    expect(onChange).toHaveBeenCalledWith([sections[1], sections[0]]);
  });
});
