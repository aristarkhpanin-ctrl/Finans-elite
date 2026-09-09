// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuditRequisites as View } from "../api/audit";
import { AuditRequisites } from "./AuditRequisites";

/**
 * Реквизиты документа и подписи (Прил. Х).
 *
 * Экран показывает **состояние документа**, а не только поля: подписан он или остаётся
 * рабочим материалом, и что не так с введённым. Оговорки приходят из ядра — здесь их
 * не сочиняют, иначе экран разошёлся бы с бумагой.
 */

afterEach(cleanup);

function view(over: Partial<View> = {}): View {
  return {
    filled: false, signed: false, number: "", date: null, addressee: "",
    subject_full_name: "", subject_inn: "", subject_ogrn: "", subject_address: "",
    signatures: [],
    caveats: ["Документ не подписан: ни составитель, ни утверждающий не указаны. "
              + "Это рабочий материал, а не заключение."],
    not_computed: ["Сверка реквизитов с ЕГРЮЛ — доступа к реестру у платформы нет."],
    ...over,
  };
}

describe("Реквизиты документа и подписи", () => {
  it("неподписанный документ назван рабочим материалом", () => {
    render(<AuditRequisites value={{}} view={view()} onChange={() => {}} />);
    // Дважды: состоянием документа сверху и оговоркой ядра — теми же словами, что
    // напечатаны на бланке.
    expect(screen.getAllByText(/не подписан/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/рабочий материал/).length).toBe(2);
  });

  it("подписанный документ называет подписантов поимённо", () => {
    render(<AuditRequisites value={{}} onChange={() => {}} view={view({
      signed: true, filled: true,
      signatures: [{ name: "И. Петров", role: "Аналитик" }], caveats: [],
    })} />);
    expect(screen.getByText(/Документ подписан: И. Петров/)).toBeTruthy();
  });

  it("правка поля отдаётся наверх, а не копится в компоненте", () => {
    const onChange = vi.fn();
    render(<AuditRequisites value={{ number: "ДД-1" }} view={view()} onChange={onChange} />);
    fireEvent.change(screen.getByDisplayValue("ДД-1"), { target: { value: "ДД-2" } });
    expect(onChange).toHaveBeenCalledWith({ number: "ДД-2" });
  });

  it("пустая дата возвращается как null, а не как пустая строка", () => {
    // `""` в модели прошёл бы валидацию даты как ошибка; «даты нет» — это null.
    const onChange = vi.fn();
    render(<AuditRequisites value={{ date: "2026-09-05" }} view={view()}
                            onChange={onChange} />);
    fireEvent.change(screen.getByDisplayValue("2026-09-05"), { target: { value: "" } });
    expect(onChange).toHaveBeenCalledWith({ date: null });
  });

  it("оговорки ядра показываются теми же словами, что на бумаге", () => {
    render(<AuditRequisites value={{ subject_inn: "7707083894" }} onChange={() => {}}
                            view={view({ caveats: ["ИНН «7707083894» не проходит "
                              + "проверку контрольной цифры — похоже на опечатку."] })} />);
    expect(screen.getByText(/контрольной цифры/)).toBeTruthy();
    // Введённое не выбрасывается: сверить реквизит с реестром платформа не может.
    expect(screen.getByDisplayValue("7707083894")).toBeTruthy();
  });

  it("чего платформа не делает — сказано на экране", () => {
    render(<AuditRequisites value={{}} view={view()} onChange={() => {}} />);
    expect(screen.getByText(/ЕГРЮЛ/)).toBeTruthy();
  });

  it("при несохранённых правках состояние честно названо отстающим", () => {
    // Пересчитать правила на экране значило бы завести их вторую копию — а копии
    // расходятся молча. Поэтому отставание называется, а не прячется.
    render(<AuditRequisites value={{ executor_name: "И. Петров" }} view={view()} stale
                            onChange={() => {}} />);
    expect(screen.getByText(/по сохранённой версии дела/)).toBeTruthy();
  });

  it("у сохранённого дела приписки об отставании нет", () => {
    render(<AuditRequisites value={{}} view={view()} onChange={() => {}} />);
    expect(screen.queryByText(/по сохранённой версии дела/)).toBeNull();
  });
});
