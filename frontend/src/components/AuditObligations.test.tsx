// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuditObligations as Register, Obligation } from "../api/audit";
import { AuditObligations } from "./AuditObligations";

/**
 * Обязательства и залоги. Проверяются решения методики, которые легко потерять при
 * следующей правке экрана: два итога не сводятся в один, расхождение с балансом
 * названо всегда, «по требованию» ≠ «срок не заполнен», а пустая ставка — не 0%.
 */

afterEach(cleanup);

function reg(over: Partial<Register> = {}): Register {
  return {
    rows: [], balance_debt: "0", off_balance: "0", reported_debt: "0", discrepancy: "0",
    reconciled: true, buckets: [], pledged_total: "0", free_assets: null,
    pledged_share: null, covenants_breached: 0, covenants_unknown: 0, ...over,
  };
}

function row(over: Partial<Register["rows"][number]> = {}): Register["rows"][number] {
  return {
    creditor: "Сбербанк", contract: "КД-4417/24", kind: "credit",
    kind_label: "Кредит банка", off_balance: false, amount: "400", rate: "0.158",
    maturity: "2029", on_demand: false, collateral: "подвижной состав",
    pledged_amount: "0", covenant: "", covenant_status: "unknown", covenant_note: "",
    ...over,
  };
}

function obligation(over: Partial<Obligation> = {}): Obligation {
  return {
    creditor: "Сбербанк", contract: "КД-4417/24", kind: "credit", amount: "400",
    rate: null, maturity_year: 2029, on_demand: false, collateral: "",
    pledged_amount: "", covenant: "", covenant_status: "unknown", covenant_note: "",
    ...over,
  };
}

function show(register: Partial<Register> = {}, opts: {
  obligations?: Obligation[]; onChange?: (next: Obligation[]) => void;
} = {}) {
  render(<AuditObligations register={reg(register)}
                           obligations={opts.obligations ?? []}
                           onChange={opts.onChange ?? (() => {})} />);
}

describe("Обязательства и залоги", () => {
  it("забалансовое показано отдельным итогом и сказано, что складывать нельзя", () => {
    // Главное правило модуля: сложить — значит утверждать, что поручительство
    // уже наступило; спрятать — что его нет.
    show({ rows: [row(), row({ kind: "guarantee", off_balance: true, amount: "180" })],
           balance_debt: "400", off_balance: "180" });
    expect(screen.getByText("Долг в балансе")).toBeTruthy();
    expect(screen.getByText("Забалансовые обязательства")).toBeTruthy();
    const note = screen.getByText(/Забалансовое обязательство ещё не наступило/);
    expect(note.textContent).toContain("не складываются");
    // Общей суммы (580) на экране быть не должно.
    expect(screen.queryByText(/580/)).toBeNull();
  });

  it("расхождение с балансом названо суммой и причиной", () => {
    show({ rows: [row()], balance_debt: "400", reported_debt: "520",
           discrepancy: "120", reconciled: false });
    expect(screen.getByText(/Часть долга не названа/)).toBeTruthy();
  });

  it("реестр шире баланса — другая причина, а не та же", () => {
    show({ rows: [row({ amount: "700" })], balance_debt: "700", reported_debt: "520",
           discrepancy: "-180", reconciled: false });
    expect(screen.getByText(/Реестр шире баланса/)).toBeTruthy();
  });

  it("сошедшийся реестр тоже говорит об этом, а не молчит", () => {
    show({ rows: [row({ amount: "520" })], balance_debt: "520", reported_debt: "520",
           reconciled: true });
    expect(screen.getByText(/Реестр сходится с балансом/)).toBeTruthy();
  });

  it("пустой реестр объявлен незаполненным, а не сошедшимся", () => {
    // «Сверка пройдена» на пустом реестре была бы враньём: сверять нечего.
    show({ reported_debt: "520" });
    expect(screen.getByText(/Реестр пуст, сверять нечего/)).toBeTruthy();
    expect(screen.queryByText(/Реестр сходится/)).toBeNull();
  });

  it("график подписан как долг по годам погашения, а не платежи года", () => {
    show({ buckets: [{ label: "2026", amount: "100", kind: "year" },
                     { label: "2027", amount: "420", kind: "year" }] });
    expect(screen.getByText("Долг по годам погашения")).toBeTruthy();
    const hint = screen.getByText(/график платежей/);
    expect(hint.textContent).toContain("Это не график платежей");
    expect(hint.textContent).toContain("выдумать условия");
  });

  it("незаполненный срок не разносится по годам и назван отдельно", () => {
    show({ buckets: [{ label: "2026", amount: "100", kind: "year" },
                     { label: "срок не указан", amount: "50", kind: "unknown" }] });
    expect(screen.getByText(/срок погашения не заполнен/)).toBeTruthy();
  });

  it("доля заложенного не считается, когда активов нет", () => {
    // «0% активов» при нулевом активе — деление, которого не существует.
    show({ rows: [row({ pledged_amount: "50" })], pledged_total: "50",
           pledged_share: null, free_assets: null });
    expect(screen.getByText(/считать не от чего/)).toBeTruthy();
  });

  it("свободные активы показаны как предел нового финансирования", () => {
    show({ rows: [row()], pledged_total: "840", pledged_share: "0.75",
           free_assets: "280" });
    expect(screen.getByText("75% активов")).toBeTruthy();
    expect(screen.getByText(/без согласия текущих кредиторов/)).toBeTruthy();
  });

  it("непроверенный ковенант объявлен непроверенным, а не соблюдённым", () => {
    show({ rows: [row({ covenant: "Долг/EBITDA ≤ 2.5×" })], covenants_unknown: 1 });
    expect(screen.getByText(/не считается соблюдённым/)).toBeTruthy();
  });

  it("нарушенный ковенант объясняет последствие — досрочное истребование", () => {
    show({ rows: [row({ covenant: "Долг/EBITDA ≤ 2.5×", covenant_status: "breached" })],
           covenants_breached: 1 });
    expect(screen.getByText(/досрочного истребования/)).toBeTruthy();
  });

  it("пустая ставка уходит наверх как «не указана», а не как ноль", () => {
    // Беспроцентный займ (0%) и займ без указанной ставки — разные факты.
    const onChange = vi.fn();
    show({}, { obligations: [obligation({ rate: "0.158" })], onChange });
    fireEvent.change(screen.getByLabelText("Обязательство 1: ставка"),
                     { target: { value: "" } });
    expect(onChange.mock.calls[0][0][0].rate).toBeNull();
  });

  it("ставка вводится в процентах, а хранится долей", () => {
    const onChange = vi.fn();
    show({}, { obligations: [obligation()], onChange });
    fireEvent.change(screen.getByLabelText("Обязательство 1: ставка"),
                     { target: { value: "15,8" } });
    expect(onChange.mock.calls[0][0][0].rate).toBe("0.158");
  });

  it("набираемую запятую поле не съедает", () => {
    // Поле, выведенное из модели пересчётом, стирало бы «15,» обратно в «15», и
    // десятичную ставку было бы не ввести вовсе.
    show({}, { obligations: [obligation()] });
    const input = screen.getByLabelText("Обязательство 1: ставка") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "16," } });
    expect(input.value).toBe("16,");
  });

  it("в поле ввода ставка без мусора двоичной дроби", () => {
    // `0.164 × 100` во float даёт 16.400000000000002 — ровно это и стояло в поле.
    // Сдвиг запятой считается строкой, поэтому дробь остаётся такой, какой введена.
    show({}, { obligations: [obligation({ rate: "0.164" })] });
    expect((screen.getByLabelText("Обязательство 1: ставка") as HTMLInputElement).value)
      .toBe("16.4");
  });

  it("ставка в своде показана процентом", () => {
    show({ rows: [row({ rate: "0.164" })] });
    expect(screen.getByText("16,4%")).toBeTruthy();
  });

  it("«по требованию» стирает год погашения, а не спорит с ним", () => {
    const onChange = vi.fn();
    show({}, { obligations: [obligation({ maturity_year: 2029 })], onChange });
    fireEvent.click(screen.getByLabelText("По требованию"));
    expect(onChange.mock.calls[0][0][0]).toMatchObject({ on_demand: true,
                                                         maturity_year: null });
  });

  it("вид обязательства меняет подпись суммы: остаток долга или сумма поручительства", () => {
    const { rerender } = render(
      <AuditObligations register={reg()} obligations={[obligation()]}
                        onChange={() => {}} />);
    expect(screen.getByText("Остаток долга")).toBeTruthy();
    rerender(<AuditObligations register={reg()}
                               obligations={[obligation({ kind: "guarantee" })]}
                               onChange={() => {}} />);
    expect(screen.getByText("Сумма обязательства")).toBeTruthy();
  });

  it("пустой ввод объясняет, что молчание реестра — не «обязательств нет»", () => {
    show();
    expect(screen.getByText(/это «не заполнено», а не/)).toBeTruthy();
  });

  it("кнопка удаления называет договор, а не только действие", () => {
    // Иначе на экране с пятью кредитами все кнопки имеют одно имя.
    show({}, { obligations: [obligation({ creditor: "Альфа-Банк" })] });
    expect(screen.getByTitle("Удалить обязательство «Альфа-Банк»")).toBeTruthy();
  });

  it("добавление создаёт пустое обязательство под заполнение", () => {
    const onChange = vi.fn();
    show({}, { onChange });
    fireEvent.click(screen.getByText(/Обязательство$/));
    expect(onChange.mock.calls[0][0]).toHaveLength(1);
    expect(onChange.mock.calls[0][0][0]).toMatchObject({ kind: "credit",
                                                         covenant_status: "unknown",
                                                         rate: null,
                                                         maturity_year: null });
  });
});
