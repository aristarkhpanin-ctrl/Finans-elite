// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { OperatingPlan } from "../../api/model";
import type { CostsImport } from "../../costsXlsx";
import { CostsTab } from "./CostsTab";

/** Импорт издержек (G13): отчёт называет созданное с умолчаниями и непринятое. */

const parseCostsXlsx = vi.fn();
vi.mock("../../costsXlsx", async (orig) => ({
  ...(await orig<typeof import("../../costsXlsx")>()),
  parseCostsXlsx: (...a: unknown[]) => parseCostsXlsx(...a),
}));

afterEach(cleanup);

const plan: OperatingPlan = { products: [], sales: [], production: [], direct_costs: [],
                              fixed_costs: [], staff: [] };

function report(changed: boolean): CostsImport {
  return {
    operating: { ...plan, fixed_costs: [{ name: "Связь", function: "admin", amount: ["5"],
                                          payment_delay_months: 0 }] },
    changed,
    sheets: [
      { sheet: "Прямые издержки", absent: true, updated: [], created: [], defaults: "",
        problems: [] },
      { sheet: "Постоянные издержки", absent: false, updated: [], created: ["Связь"],
        defaults: "Созданные статьи: оплата без отсрочки.", problems: [] },
      { sheet: "Персонал", absent: false, updated: [], created: [], defaults: "",
        problems: ["строка 2 («Кассир»): не задан оклад — строка не применена"] },
    ],
  };
}

async function importFile(onChange = vi.fn()) {
  render(<CostsTab n={1} operating={plan} onChange={onChange} />);
  const input = screen.getByLabelText("Файл XLSX с издержками и персоналом");
  fireEvent.change(input, { target: { files: [new File(["x"], "costs.xlsx")] } });
  await screen.findByText("Импорт из Excel");
  return onChange;
}

describe("Импорт издержек и персонала", () => {
  it("созданное — с умолчаниями, непринятое — с причиной, отсутствующий лист назван", async () => {
    parseCostsXlsx.mockResolvedValue(report(true));
    const onChange = await importFile();
    expect(onChange).toHaveBeenCalledWith(report(true).operating);
    expect(screen.getByText(/Создано: Связь/)).toBeTruthy();
    expect(screen.getByText(/оплата без отсрочки/)).toBeTruthy();
    expect(screen.getByText(/не задан оклад/)).toBeTruthy();
    expect(screen.getByText(/Листа нет в файле — раздел не тронут/)).toBeTruthy();
    expect(screen.getByText(/не удаляются/)).toBeTruthy();
  });

  it("ничего не применилось — модель не трогается, и это сказано", async () => {
    parseCostsXlsx.mockResolvedValue(report(false));
    const onChange = await importFile();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("Модель не изменилась")).toBeTruthy();
  });
});
