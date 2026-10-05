// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, AxiosHeaders } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OrgLogo } from "../../api/branding";

/**
 * Вкладка «Оформление» (L9). Проверяется то, что легко потерять: правила приёма — с
 * сервера, а не пересказом; отказ сервера доходит до человека своими словами («SVG не
 * принимается, потому что…»); мегабайты в сеть не уходят; без права логотип виден, но
 * не меняется — и сказано почему.
 */

const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));
const getOrgLogo = vi.fn();
const setOrgLogo = vi.fn();
const deleteOrgLogo = vi.fn();
vi.mock("../../api/branding", async (orig) => ({
  ...(await orig<typeof import("../../api/branding")>()),
  getOrgLogo: (...a: unknown[]) => getOrgLogo(...a),
  setOrgLogo: (...a: unknown[]) => setOrgLogo(...a),
  deleteOrgLogo: (...a: unknown[]) => deleteOrgLogo(...a),
}));

const { BrandingTab } = await import("./BrandingTab");

const RULES = ["PNG или JPEG до 256 КБ. SVG не принимается: в нём бывает исполняемый код."];
const none: OrgLogo = { present: false, organization: "ООО «Ромашка»", max_bytes: 262144,
                        rules: RULES } as OrgLogo;
const set: OrgLogo = {
  ...none, present: true, mime: "image/png", kind: "PNG", size: 2048, width: 400, height: 120,
  updated_at: "2026-10-05T09:00:00Z", updated_by: "owner@e.ru",
  data_url: "data:image/png;base64,AAAA",
} as OrgLogo;

function show(canManage = true) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <BrandingTab orgId="o1" orgName="ООО «Ромашка»" canManage={canManage} />
    </QueryClientProvider>,
  );
}

const file = (bytes: number, name = "logo.png", type = "image/png") =>
  new File([new Uint8Array(bytes)], name, { type });

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("логотип в документах", () => {
  it("без логотипа сказано, чем выходят документы, и правила — с сервера", async () => {
    getOrgLogo.mockResolvedValue(none);
    show();
    expect(await screen.findByText(/Логотипа нет — документы выходят с маркой платформы/))
      .toBeTruthy();
    expect(screen.getByText(RULES[0])).toBeTruthy();
    expect(screen.getByRole("button", { name: "Загрузить PNG или JPEG" })).toBeTruthy();
  });

  it("загрузка отправляет содержимое без префикса data: и показывает лист с логотипом", async () => {
    getOrgLogo.mockResolvedValue(none);
    setOrgLogo.mockResolvedValue(set);
    show();
    const input = await screen.findByLabelText("Файл логотипа");
    fireEvent.change(input, { target: { files: [file(3)] } });
    await waitFor(() => expect(setOrgLogo).toHaveBeenCalled());
    expect(setOrgLogo.mock.calls[0][0]).toBe("o1");
    expect(setOrgLogo.mock.calls[0][1]).toBe("AAAA");          // три нулевых байта в base64
    expect(await screen.findByRole("img", { name: "Логотип «ООО «Ромашка»»" })).toBeTruthy();
    expect(screen.getByText(/PNG · 2 КБ · 400×120 px · поставил owner@e.ru/)).toBeTruthy();
  });

  it("отказ сервера доходит своими словами", async () => {
    getOrgLogo.mockResolvedValue(none);
    const reason = "SVG не принимается: это текст с разметкой, и в нём бывает исполняемый код.";
    setOrgLogo.mockRejectedValue(new AxiosError("422", "ERR", undefined, undefined, {
      status: 422, statusText: "", headers: {}, config: { headers: new AxiosHeaders() },
      data: { detail: reason },
    }));
    show();
    fireEvent.change(await screen.findByLabelText("Файл логотипа"),
                     { target: { files: [file(10, "logo.svg", "image/svg+xml")] } });
    await waitFor(() => expect(toast).toHaveBeenCalledWith(reason, { kind: "error" }));
  });

  it("файл больше предела не уходит в сеть, а предел назван числом", async () => {
    getOrgLogo.mockResolvedValue(none);
    show();
    fireEvent.change(await screen.findByLabelText("Файл логотипа"),
                     { target: { files: [file(300 * 1024)] } });
    expect(setOrgLogo).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith("Логотип больше 256 КБ (300 КБ) — уменьшите файл",
                                       { kind: "warn" });
  });

  it("убрать логотип можно, и сказано, чем выйдут документы", async () => {
    getOrgLogo.mockResolvedValueOnce(set).mockResolvedValue(none);
    deleteOrgLogo.mockResolvedValue(undefined);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Убрать логотип" }));
    await waitFor(() => expect(deleteOrgLogo).toHaveBeenCalledWith("o1"));
    expect(toast).toHaveBeenCalledWith("Логотип убран — документы выходят с маркой платформы",
                                       { kind: "success" });
  });

  it("без права логотип виден, но не меняется — и сказано почему", async () => {
    getOrgLogo.mockResolvedValue(set);
    show(false);
    expect(await screen.findByRole("img", { name: "Логотип «ООО «Ромашка»»" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /логотип/i })).toBeNull();
    expect(screen.getByText(/может владелец или администратор организации/)).toBeTruthy();
  });
});
