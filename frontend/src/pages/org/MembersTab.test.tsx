// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Member } from "../../api/org";
import { MembersTab } from "./MembersTab";

/**
 * Участники: выдача ссылки входа. Это единственный путь восстановления пароля в
 * продукте, и у него две особенности, которые легко потерять при правке экрана —
 * ссылка передаётся лично (писем платформа не шлёт) и владельцу она не выдаётся
 * вовсе, иначе администратор сбросил бы ему пароль и забрал организацию.
 */

const getMembers = vi.fn();
const issueAccessLink = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getMembers: (...a: unknown[]) => getMembers(...a),
  issueAccessLink: (...a: unknown[]) => issueAccessLink(...a),
}));

const toast = vi.fn();
vi.mock("../../components/Toast", () => ({ useToast: () => toast }));

const member = (over: Partial<Member> = {}): Member => ({
  user_id: "u2", email: "k@e.ru", full_name: "Коллега", role: "analyst",
  invite_token: null, ...over,
} as Member);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getMembers.mockResolvedValue([
    member({ user_id: "u1", email: "own@e.ru", full_name: "Владелец", role: "owner" }),
    member(),
  ]);
});

async function show(myRole = "owner") {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <MembersTab orgId="o1" myRole={myRole} myUserId="u1" />
    </QueryClientProvider>,
  );
  await screen.findByText("Коллега");
}

const linkButton = (name: string) =>
  screen.queryByTitle(`Выдать ссылку входа: ${name}`);

describe("Ссылка входа участнику", () => {
  it("выдаётся по кнопке и показывается для передачи лично", async () => {
    issueAccessLink.mockResolvedValue({ user_id: "u2", email: "k@e.ru",
                                        kind: "reset", token: "tok" });
    await show();
    fireEvent.click(linkButton("Коллега")!);
    await screen.findByText("Ссылка для сброса пароля");
    const field = screen.getByLabelText("Ссылка входа") as HTMLTextAreaElement;
    expect(field.value).toContain("/activate?token=tok");
    expect(screen.getByText(/Писем платформа не отправляет/)).toBeTruthy();
  });

  it("для участника без пароля это приглашение заново, и так и написано", async () => {
    issueAccessLink.mockResolvedValue({ user_id: "u2", email: "k@e.ru",
                                        kind: "invite", token: "tok" });
    await show();
    fireEvent.click(linkButton("Коллега")!);
    await screen.findByText("Ссылка приглашения");
    expect(screen.getByText(/приглашение заново, взамен потерянного/)).toBeTruthy();
  });

  it("владельцу кнопка не показывается", async () => {
    // Иначе администратор сбросил бы ему пароль и забрал организацию вместе с тарифом.
    await show();
    expect(linkButton("Владелец")).toBeNull();
  });

  it("без прав управления участниками кнопки нет", async () => {
    await show("analyst");
    expect(linkButton("Коллега")).toBeNull();
  });

  it("отказ сервера показывается его же словами", async () => {
    // У отказа содержательная причина (владелец, несколько организаций) — своя
    // формулировка на фронте разошлась бы с правилом на бэкенде.
    issueAccessLink.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409, data: { detail: "Участник состоит и в других организациях." } },
    });
    await show();
    fireEvent.click(linkButton("Коллега")!);
    await waitFor(() => expect(toast).toHaveBeenCalledWith(
      "Участник состоит и в других организациях.", { kind: "error" }));
  });
});
