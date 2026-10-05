// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ShareLink, ShareLinkCreated, ShareLinks as ShareLinksOut } from "../api/share";

/**
 * «Поделиться» (L4): отправитель видит всё, что открыто наружу, — кому, до какого числа,
 * сколько раз открывали; секрет показывается один раз, а оговорки — с сервера.
 */

const toast = vi.fn();
vi.mock("./Toast", () => ({ useToast: () => toast }));

const listShareLinks = vi.fn();
const createShareLink = vi.fn();
const revokeShareLink = vi.fn();
vi.mock("../api/share", async (orig) => ({
  ...(await orig<typeof import("../api/share")>()),
  listShareLinks: (id: string) => listShareLinks(id),
  createShareLink: (id: string, body: unknown) => createShareLink(id, body),
  revokeShareLink: (id: string, linkId: string) => revokeShareLink(id, linkId),
}));
const listVersions = vi.fn();
vi.mock("../api/versions", () => ({ listVersions: (id: string) => listVersions(id) }));

const { ShareLinks, linkOpens, linkState } = await import("./ShareLinks");

const base: ShareLink = {
  id: "l1", label: "Сбербанк, кредитный комитет", version_id: "v1",
  version_label: "Отправлено: Сбербанк (04.10.2026)", created_at: "2026-10-04T10:00:00Z",
  created_by: "owner@e.ru", expires_at: "2026-11-03T10:00:00Z", revoked_at: null,
  revoked_by: "", state: "active", opens: 0, last_opened_at: null,
};

const listed: ShareLinksOut = {
  links: [
    { ...base, opens: 3, last_opened_at: "2026-10-05T09:30:00Z" },
    { ...base, id: "l2", label: "Фонд", state: "revoked", revoked_at: "2026-10-06T12:00:00Z",
      revoked_by: "owner@e.ru" },
    { ...base, id: "l3", label: "Инвестор", state: "expired", expires_at: "2026-10-01T00:00:00Z" },
  ],
  notes: ["Кто открывает ссылку, отправителю не известно — её могли переслать."],
};

function show() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ShareLinks open onClose={vi.fn()} projectId="p1" />
    </QueryClientProvider>,
  );
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("состояние ссылки словами", () => {
  it("закрытая, истёкшая и живая — разными словами", () => {
    expect(linkState(base)).toMatch(/^открыта до /);
    expect(linkState(listed.links[1])).toMatch(/^закрыта .* · owner@e\.ru$/);
    expect(linkState(listed.links[2])).toMatch(/^срок истёк /);
  });

  it("ноль открытий сказан словами, а не цифрой", () => {
    expect(linkOpens(base)).toBe("ещё не открывали");
    expect(linkOpens(listed.links[0])).toMatch(/^открывали 3 раза, последний — /);
  });
});

describe("окно «Поделиться»", () => {
  it("показывает, что открыто наружу, и оговорки сервера", async () => {
    listShareLinks.mockResolvedValue(listed);
    listVersions.mockResolvedValue([]);
    show();
    await screen.findByText("Фонд");
    expect(screen.getByText("Сбербанк, кредитный комитет")).toBeTruthy();
    expect(document.body.textContent).toContain("Кто открывает ссылку, отправителю не известно");
    // Закрыть можно только живую ссылку.
    expect(screen.getAllByRole("button", { name: /^Закрыть ссылку/ })).toHaveLength(1);
  });

  it("без имени получателя ссылку не открыть", async () => {
    listShareLinks.mockResolvedValue({ links: [], notes: [] });
    listVersions.mockResolvedValue([]);
    show();
    await screen.findByText(/Ссылок ещё не открывали/);
    const submit = screen.getByRole("button", { name: "Открыть ссылку" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Для кого"), { target: { value: "  " } });
    expect(submit.disabled).toBe(true);
  });

  it("секрет показывается один раз — полным адресом и с оговорками", async () => {
    listShareLinks.mockResolvedValue({ links: [], notes: [] });
    listVersions.mockResolvedValue([{ id: "v9", label: "План для комитета" }]);
    const created: ShareLinkCreated = {
      ...base, token: "fs_secret", path: "/s/fs_secret",
      notes: ["Ссылка показывается один раз: платформа хранит только её отпечаток."],
    };
    createShareLink.mockResolvedValue(created);
    show();
    await screen.findByRole("option", { name: "План для комитета" });
    fireEvent.change(screen.getByLabelText("Для кого"), { target: { value: " Сбербанк " } });
    fireEvent.change(screen.getByLabelText("Срок"), { target: { value: "90" } });
    fireEvent.change(screen.getByLabelText("Что открыть"), { target: { value: "v9" } });
    fireEvent.click(screen.getByRole("button", { name: "Открыть ссылку" }));
    const field = await screen.findByLabelText("Ссылка") as HTMLInputElement;
    expect(createShareLink).toHaveBeenCalledWith("p1", { label: "Сбербанк", days: 90, version_id: "v9" });
    expect(field.value).toBe(`${window.location.origin}/s/fs_secret`);
    expect(document.body.textContent).toContain("показывается один раз");
  });

  it("отказ сервера — его словами", async () => {
    listShareLinks.mockResolvedValue({ links: [], notes: [] });
    listVersions.mockResolvedValue([]);
    createShareLink.mockRejectedValue({
      isAxiosError: true, response: { status: 403, data: { detail: "Организация в режиме чтения." } },
    });
    show();
    fireEvent.change(await screen.findByLabelText("Для кого"), { target: { value: "Банк" } });
    fireEvent.click(screen.getByRole("button", { name: "Открыть ссылку" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent)
      .toBe("Организация в режиме чтения."));
  });

  it("закрыть — одним нажатием, с подтверждением тостом", async () => {
    listShareLinks.mockResolvedValue(listed);
    listVersions.mockResolvedValue([]);
    revokeShareLink.mockResolvedValue(undefined);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Закрыть ссылку для «Сбербанк, кредитный комитет»" }));
    await waitFor(() => expect(revokeShareLink).toHaveBeenCalledWith("p1", "l1"));
    await waitFor(() => expect(toast).toHaveBeenCalledWith(
      "Ссылка закрыта — по ней план больше не откроется", { kind: "success" }));
  });
});
