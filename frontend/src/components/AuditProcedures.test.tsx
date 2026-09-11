// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AuditProcedure,
  AuditProcedures as Report,
  CustomProcedure,
  ProcedureMark,
} from "../api/audit";
import { AuditProcedures } from "./AuditProcedures";

/**
 * Чек-лист процедур. Проверяются решения методики, которые легко потерять при
 * следующей правке экрана: системную процедуру нельзя отметить вручную, «нет данных»
 * не выглядит пройденным, границы проверки стоят рядом с охватом, а снятие без
 * причины предупреждает, что не применится.
 */

afterEach(cleanup);

function proc(over: Partial<AuditProcedure> = {}): AuditProcedure {
  return {
    code: "balance_identity", group: "Отчётность и её целостность",
    title: "Актив равен пассиву во всех периодах", source: "system",
    method: "инвариант ввода", status: "pass",
    detail: "Актив равен пассиву во всех введённых периодах.", findings: [], ...over,
  };
}

function report(over: Partial<Report> = {}): Report {
  return {
    items: [proc()], total: 1, closed: 1, passed: 1, findings: 0, no_data: 0,
    done: 0, skipped: 0, pending: 0, coverage: "1", limits: [], ...over,
  };
}

function show(over: Partial<Report> = {}, opts: {
  marks?: ProcedureMark[]; custom?: CustomProcedure[];
  onMarks?: (n: ProcedureMark[]) => void; onCustom?: (n: CustomProcedure[]) => void;
} = {}) {
  render(<AuditProcedures report={report(over)} marks={opts.marks ?? []}
                          custom={opts.custom ?? []}
                          onMarks={opts.onMarks ?? (() => {})}
                          onCustom={opts.onCustom ?? (() => {})} />);
}

const analyst = (over: Partial<AuditProcedure> = {}) => proc({
  code: "litigation", group: "Связанные стороны, налоги и споры",
  title: "Судебные дела и претензии", source: "analyst",
  method: "нужна картотека арбитражных дел", status: "pending", detail: "", ...over,
});

describe("Чек-лист процедур", () => {
  it("системную процедуру отметить нельзя, и сказано почему", () => {
    // Иначе «выполнено» можно объявить там, где правило не отработало, и чек-лист
    // перестанет что-либо значить. Отсутствие поля без объяснения читалось бы
    // как недоделка.
    show();
    expect(screen.getByText(/Итог выводится из прогона правила/)).toBeTruthy();
    expect(screen.queryByLabelText(/отметка/)).toBeNull();
  });

  it("у процедуры аналитика есть отметка и пояснение", () => {
    show({ items: [analyst()], total: 1, closed: 0, passed: 0, pending: 1,
           coverage: "0" });
    expect(screen.getByLabelText("Судебные дела и претензии: отметка")).toBeTruthy();
    expect(screen.getByLabelText("Судебные дела и претензии: пояснение")).toBeTruthy();
  });

  it("исполнитель назван у каждой процедуры", () => {
    // Макет подписывает «базовая · автоматически» под сверкой с картотекой судов.
    show({ items: [proc(), analyst()], total: 2 });
    expect(screen.getByText("платформа")).toBeTruthy();
    expect(screen.getByText("аналитик")).toBeTruthy();
    expect(screen.getByText("нужна картотека арбитражных дел")).toBeTruthy();
  });

  it("«нет данных» подписано как непроверенное, а не как пройденное", () => {
    show({ items: [proc({ status: "no_data",
                          detail: "Проценты к уплате не введены." })],
           total: 1, closed: 0, passed: 0, no_data: 1, coverage: "0" });
    expect(screen.getByText("Нет данных")).toBeTruthy();
    expect(screen.queryByText("Проверено")).toBeNull();
  });

  it("границы проверки стоят рядом с охватом и объясняют, зачем они", () => {
    // «Охват 70%» без перечня тех 30% читается как «почти всё проверено».
    show({ total: 10, closed: 7, coverage: "0.7",
           limits: ["Судебные дела и претензии — Процедуру выполняет аналитик; отметки нет."] });
    expect(screen.getByText("70%")).toBeTruthy();
    expect(screen.getByText("Границы проверки")).toBeTruthy();
    expect(screen.getByText(/умолчание он прочтёт как проверенное/)).toBeTruthy();
    expect(screen.getByText(/Судебные дела и претензии/)).toBeTruthy();
  });

  it("охват без границ не выдаёт себя за полноту", () => {
    show({ total: 1, closed: 1, coverage: "1" });
    expect(screen.getByText("100%")).toBeTruthy();
    expect(screen.queryByText("Границы проверки")).toBeNull();
  });

  it("отметка аналитика уходит наверх, а не теряется", () => {
    const onMarks = vi.fn();
    show({ items: [analyst()], total: 1 }, { onMarks });
    fireEvent.change(screen.getByLabelText("Судебные дела и претензии: отметка"),
                     { target: { value: "done" } });
    expect(onMarks).toHaveBeenCalledWith([
      { code: "litigation", status: "done", note: "" },
    ]);
  });

  it("существующая отметка правится, а не дублируется", () => {
    const onMarks = vi.fn();
    show({ items: [analyst()], total: 1 },
         { marks: [{ code: "litigation", status: "done", note: "проверено" }], onMarks });
    fireEvent.change(screen.getByLabelText("Судебные дела и претензии: пояснение"),
                     { target: { value: "дел нет" } });
    expect(onMarks.mock.calls[0][0]).toHaveLength(1);
    expect(onMarks.mock.calls[0][0][0].note).toBe("дел нет");
  });

  it("при снятии поле причины называется обязательным", () => {
    show({ items: [analyst()], total: 1 },
         { marks: [{ code: "litigation", status: "skipped", note: "" }] });
    const note = screen.getByLabelText("Судебные дела и претензии: пояснение");
    expect(note.getAttribute("placeholder")).toContain("обязательно");
  });

  it("отраслевого каталога нет — и это объявлено решением, а не пробелом", () => {
    show();
    expect(screen.getByText(/Отраслевого каталога у платформы нет намеренно/)).toBeTruthy();
  });

  it("своя процедура добавляется пустой под заполнение", () => {
    const onCustom = vi.fn();
    show({}, { onCustom });
    fireEvent.click(screen.getByText(/Процедура$/));
    expect(onCustom).toHaveBeenCalledWith([{ title: "", status: "pending", note: "" }]);
  });

  it("своя процедура без названия предупреждает, что не попадёт в заключение", () => {
    show({}, { custom: [{ title: "", status: "pending", note: "" }] });
    expect(screen.getByText(/Без названия процедура не существует/)).toBeTruthy();
  });

  it("своя процедура, снятая без причины, предупреждает, что снятие не применится", () => {
    show({}, { custom: [{ title: "Сверить полисы", status: "skipped", note: "" }] });
    expect(screen.getByText(/Снятие без причины не применяется/)).toBeTruthy();
  });

  it("заполненная причина снимает предупреждение", () => {
    show({}, { custom: [{ title: "Сверить полисы", status: "skipped",
                          note: "полисов нет" }] });
    expect(screen.queryByText(/Снятие без причины не применяется/)).toBeNull();
  });

  it("кнопка удаления называет процедуру, а не только действие", () => {
    show({}, { custom: [{ title: "Сверить полисы", status: "pending", note: "" }] });
    expect(screen.getByTitle("Удалить процедуру «Сверить полисы»")).toBeTruthy();
  });

  it("свои процедуры не дублируются в блоках каталога", () => {
    // Они приходят в items с кодом custom:N — редактируются отдельным блоком.
    show({ items: [proc(), proc({ code: "custom:0", group: "Свои процедуры",
                                  title: "Сверить полисы", source: "analyst",
                                  method: "процедура аналитика", status: "pending" })],
           total: 2 },
         { custom: [{ title: "Сверить полисы", status: "pending", note: "" }] });
    expect(screen.queryByText("Свои процедуры", { selector: ".audit-block__title" }))
      .toBeTruthy();
    // В каталожных блоках своей процедуры нет — только в редакторе (как значение поля).
    expect(screen.queryAllByText("Сверить полисы")).toHaveLength(0);
  });

  it("процедуры сгруппированы по разделам каталога", () => {
    show({ items: [proc(), analyst()], total: 2 });
    const block = screen.getByText("Отчётность и её целостность").closest(".audit-block")!;
    expect(within(block as HTMLElement)
      .getByText("Актив равен пассиву во всех периодах")).toBeTruthy();
    expect(screen.getByText("Связанные стороны, налоги и споры")).toBeTruthy();
  });
});
