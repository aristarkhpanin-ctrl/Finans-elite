// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BillingDocuments as Docs, Plan } from "../../api/org";
import { BillingDocuments } from "./BillingDocuments";

/**
 * Счета, акты и реквизиты (G6). Проверяется, что экран **не додумывает**: причины, по
 * которым документа нет, и проблемы реквизитов показываются словами сервера; чего
 * платформа не формирует вовсе, сказано рядом со списком; бланк скачивается с сервера,
 * а не рисуется здесь.
 */

const getBillingDocuments = vi.fn();
const getRequisites = vi.fn();
const saveRequisites = vi.fn();
const createInvoice = vi.fn();
const downloadBillingDocument = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getBillingDocuments: (...a: unknown[]) => getBillingDocuments(...a),
  getRequisites: (...a: unknown[]) => getRequisites(...a),
  saveRequisites: (...a: unknown[]) => saveRequisites(...a),
  createInvoice: (...a: unknown[]) => createInvoice(...a),
  downloadBillingDocument: (...a: unknown[]) => downloadBillingDocument(...a),
}));
const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));

afterEach(cleanup);

const PLANS = [
  { code: "free", product: "business", name: "Бесплатный", price_rub: 0,
    price_on_request: false },
  { code: "team", product: "business", name: "Команда", price_rub: 2900,
    price_on_request: false },
] as Plan[];

const INVOICE = { id: "d1", kind: "invoice", number: 1, doc_date: "2026-09-26",
                  title: "Счёт № 1 от 26.09.2026", plan_name: "Команда", months: 12,
                  amount_rub: 34800 };

function docs(over: Partial<Docs> = {}): Docs {
  return { documents: [], upcoming: [], seller_ready: true, seller_note: "",
           not_issued: "Счёт-фактура и УПД не формируются.", ...over } as Docs;
}

beforeEach(() => {
  vi.clearAllMocks();
  getBillingDocuments.mockResolvedValue(docs());
  getRequisites.mockResolvedValue({ legal_name: "ООО «Клиент»", inn: "7736050003",
    kpp: "772801001", legal_address: "Москва", problems: [] });
  saveRequisites.mockImplementation((_o: string, body: object) =>
    Promise.resolve({ ...body, problems: [] }));
  createInvoice.mockResolvedValue(INVOICE);
  downloadBillingDocument.mockResolvedValue(undefined);
});

async function show(canManage = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}>
    <BillingDocuments orgId="o1" canManage={canManage} plans={PLANS} />
  </QueryClientProvider>);
  await screen.findByText("Реквизиты организации");
  await screen.findByDisplayValue("ООО «Клиент»");
}

describe("Документы об оплате", () => {
  it("чего платформа не формирует, сказано рядом со списком", async () => {
    await show();
    expect(await screen.findByText("Счёт-фактура и УПД не формируются.")).toBeTruthy();
  });

  it("неготовые реквизиты продавца названы словами сервера", async () => {
    getBillingDocuments.mockResolvedValue(docs({ seller_ready: false,
      seller_note: "Платформа не указала свои реквизиты полностью." }));
    await show();
    expect(await screen.findByText("Платформа не указала свои реквизиты полностью."))
      .toBeTruthy();
  });

  it("проблема реквизитов организации видна, пока её не поправили", async () => {
    getRequisites.mockResolvedValue({ legal_name: "ООО «Клиент»", inn: "7736050004",
      kpp: "772801001", legal_address: "Москва",
      problems: ["ИНН «7736050004» не проходит проверку контрольной цифры"] });
    await show();
    expect(screen.getByText(/не проходит проверку контрольной цифры/)).toBeTruthy();
  });

  it("реквизиты сохраняются правкой, а без правки кнопка молчит", async () => {
    await show();
    const saveBtn = screen.getByRole("button", { name: "Сохранить реквизиты" });
    expect((saveBtn as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Адрес"), { target: { value: "Казань" } });
    fireEvent.click(saveBtn);
    await waitFor(() => expect(saveRequisites).toHaveBeenCalledWith("o1", expect.objectContaining(
      { legal_address: "Казань", inn: "7736050003" })));
  });

  it("счёт выставляется на выбранный тариф и срок и сразу скачивается", async () => {
    await show();
    fireEvent.change(screen.getByLabelText("Срок счёта"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Выставить счёт" }));
    await waitFor(() => expect(createInvoice).toHaveBeenCalledWith("o1", "team", 12));
    await waitFor(() => expect(downloadBillingDocument).toHaveBeenCalledWith("o1", INVOICE));
  });

  it("в тарифах счёта только те, у которых есть цена", async () => {
    await show();
    const options = [...(screen.getByLabelText("Тариф счёта") as HTMLSelectElement).options]
      .map((o) => o.value);
    expect(options).toEqual(["team"]);
  });

  it("документы скачиваются с сервера", async () => {
    getBillingDocuments.mockResolvedValue(docs({ documents: [INVOICE] as Docs["documents"] }));
    await show();
    fireEvent.click(await screen.findByRole("button", { name: "Скачать DOCX" }));
    await waitFor(() => expect(downloadBillingDocument).toHaveBeenCalledWith("o1", INVOICE));
  });

  it("акт, которого ещё нет, назван датой или причиной", async () => {
    getBillingDocuments.mockResolvedValue(docs({ upcoming: [
      { payment_id: "p1", paid_at: "2026-09-20T00:00:00Z", plan_name: "Команда",
        amount_rub: 2900, act_date: "2026-10-20", state: "scheduled", reason: "" },
      { payment_id: "p2", paid_at: "2026-08-01T00:00:00Z", plan_name: "Команда",
        amount_rub: 2900, act_date: null, state: "no_period",
        reason: "период этой оплаты не записан" },
    ] as Docs["upcoming"] }));
    await show();
    expect(await screen.findByText(/будет сформирован 20\.10\.2026/)).toBeTruthy();
    expect(screen.getByText("период этой оплаты не записан")).toBeTruthy();
  });

  it("без права оплаты реквизиты видны, но не правятся, и счёт не выставить", async () => {
    await show(false);
    expect((screen.getByLabelText("ИНН") as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Выставить счёт" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Сохранить реквизиты" })).toBeNull();
  });
});
