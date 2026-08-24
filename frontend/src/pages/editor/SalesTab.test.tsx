// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Company, OperatingPlan } from "../../api/model";
import { SalesTab } from "./SalesTab";

/**
 * Вкладка «Сбыт» — вход всех чисел продаж. Опасность здесь не в арифметике, а в
 * **согласованности**: продукты, ряды продаж, ряды выпуска и рецептуры живут в разных
 * массивах модели и связаны только идентификаторами. Ссылка, пережившая удаление объекта,
 * не ломает расчёт — движок её пропускает, — и потому обнаруживается не сразу, а числами,
 * которые «почему-то ниже».
 */

vi.mock("../../components/Toast", () => ({ useToast: () => vi.fn() }));

afterEach(cleanup);

const op = (over: Partial<OperatingPlan> = {}): OperatingPlan => ({
  products: [{ id: "p1", name: "Изделие" }],
  sales: [{ product_id: "p1", volume: ["10"], price: ["100"],
            payment: { prepayment_share: "0", advance_lead_months: 0, payment_delay_months: 0 } }],
  production: [],
  direct_costs: [],
  fixed_costs: [],
  staff: [],
  materials: [],
  ...over,
} as unknown as OperatingPlan);

const company = (over: Partial<Company> = {}): Company =>
  ({ starting_balance: {}, ...over }) as unknown as Company;

/** Отрисовать вкладку и вернуть перехватчики изменений модели. */
function renderTab(operating = op(), c = company()) {
  const onChange = vi.fn();
  const onCompany = vi.fn();
  render(<SalesTab n={1} operating={operating} company={c}
                   onChange={onChange} onCompany={onCompany} />);
  return { onChange, onCompany };
}

/** Последняя модель, переданная в onChange. */
const last = (fn: ReturnType<typeof vi.fn>): OperatingPlan => {
  const calls = fn.mock.calls;
  return calls[calls.length - 1][0];
};

describe("SalesTab — согласованность продуктов и рядов", () => {
  it("новый продукт получает и карточку, и ряд продаж", () => {
    const { onChange } = renderTab();
    fireEvent.click(screen.getByText(/Добавить ещё продукт/));
    const next = last(onChange);
    expect(next.products).toHaveLength(2);
    expect(next.sales).toHaveLength(2);
    // ряд привязан именно к новому продукту
    expect(next.sales[1].product_id).toBe(next.products[1].id);
  });

  it("удаление продукта уносит его ряд продаж и ряд выпуска", () => {
    const { onChange } = renderTab(op({
      production: [{ product_id: "p1", volume: ["12"] }],
    } as Partial<OperatingPlan>));
    fireEvent.click(screen.getByTitle("Удалить продукт"));
    const next = last(onChange);
    expect(next.products).toHaveLength(0);
    expect(next.sales).toHaveLength(0);
    expect(next.production).toHaveLength(0);   // осиротевшего ряда выпуска не остаётся
  });
});

describe("SalesTab — удаление не оставляет висячих ссылок", () => {
  it("удаление материала снимает его из рецептур продуктов", () => {
    const { onChange } = renderTab(op({
      materials: [{ id: "m1", name: "Сталь", unit_price: "5" }],
      products: [{ id: "p1", name: "Изделие",
                   bom: [{ material_id: "m1", qty_per_unit: "3" }] }],
    } as unknown as Partial<OperatingPlan>));

    fireEvent.click(screen.getByTitle("Удалить материал"));
    const next = last(onChange);
    expect(next.materials).toHaveLength(0);
    // ключевое: строка рецептуры не осталась висеть на удалённом материале
    expect(next.products[0].bom).toEqual([]);
  });

  it("рецептуры других материалов при этом не трогаются", () => {
    const { onChange } = renderTab(op({
      materials: [{ id: "m1", name: "Сталь", unit_price: "5" },
                  { id: "m2", name: "Краска", unit_price: "7" }],
      products: [{ id: "p1", name: "Изделие",
                   bom: [{ material_id: "m1", qty_per_unit: "3" },
                         { material_id: "m2", qty_per_unit: "1" }] }],
    } as unknown as Partial<OperatingPlan>));

    fireEvent.click(screen.getAllByTitle("Удалить материал")[0]);
    const next = last(onChange);
    expect((next.materials ?? []).map((m) => m.id)).toEqual(["m2"]);
    expect(next.products[0].bom).toEqual([{ material_id: "m2", qty_per_unit: "1" }]);
  });

  it("удаление подразделения снимает отнесение у его продуктов", () => {
    const { onChange } = renderTab(
      op({ products: [{ id: "p1", name: "Изделие", division_id: "d1" }] } as unknown as Partial<OperatingPlan>),
      company({ divisions: [{ id: "d1", name: "Розница" }] } as unknown as Partial<Company>),
    );
    fireEvent.click(screen.getByTitle("Удалить подразделение"));
    expect(last(onChange).products[0].division_id).toBeNull();
  });
});
