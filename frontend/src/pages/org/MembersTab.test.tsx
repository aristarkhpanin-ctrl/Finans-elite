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
const blockMember = vi.fn();
const unblockMember = vi.fn();
vi.mock("../../api/org", async (orig) => ({
  ...(await orig<typeof import("../../api/org")>()),
  getMembers: (...a: unknown[]) => getMembers(...a),
  issueAccessLink: (...a: unknown[]) => issueAccessLink(...a),
  blockMember: (...a: unknown[]) => blockMember(...a),
  unblockMember: (...a: unknown[]) => unblockMember(...a),
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

  /**
   * Приостановка доступа (A1). Проверяется то, что отличает её от удаления: участник
   * остаётся в списке, причина обязательна и видна, а вернуть доступ можно одной
   * кнопкой.
   */
  it("приостановленный остаётся в списке и помечен причиной", async () => {
    getMembers.mockResolvedValue([
      member({ user_id: "u1", email: "own@e.ru", full_name: "Владелец", role: "owner" }),
      member({ blocked: true, block_reason: "увольнение",
               blocked_at: "2026-09-10T10:00:00Z", blocked_by: "own@e.ru" }),
    ]);
    await show();
    // Исчезнувший из списка читался бы как удалённый — это другое состояние.
    expect(screen.getByText("Коллега")).toBeTruthy();
    expect(screen.getByTitle("увольнение")).toBeTruthy();
    expect(screen.getByText("приостановлен")).toBeTruthy();
  });

  it("причина обязательна: без неё приостановить нельзя", async () => {
    await show();
    fireEvent.click(screen.getByTitle("Приостановить доступ"));
    const submit = screen.getByText("Приостановить").closest("button")!;
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Причина приостановки"),
                     { target: { value: "увольнение" } });
    expect(submit.disabled).toBe(false);
  });

  it("приостановка уходит на сервер вместе с причиной", async () => {
    blockMember.mockResolvedValue(member({ blocked: true, block_reason: "увольнение" }));
    await show();
    fireEvent.click(screen.getByTitle("Приостановить доступ"));
    fireEvent.change(screen.getByLabelText("Причина приостановки"),
                     { target: { value: "увольнение" } });
    fireEvent.click(screen.getByText("Приостановить"));
    await waitFor(() => expect(blockMember).toHaveBeenCalledWith("o1", "u2", "увольнение"));
  });

  it("диалог предупреждает, что отзыв мгновенный", async () => {
    // Администратор должен понимать, что открытая у сотрудника вкладка перестанет
    // работать сейчас, а не завтра.
    await show();
    fireEvent.click(screen.getByTitle("Приостановить доступ"));
    expect(screen.getByText(/сразу/)).toBeTruthy();
  });

  it("доступ возвращается одной кнопкой", async () => {
    getMembers.mockResolvedValue([
      member({ user_id: "u1", email: "own@e.ru", full_name: "Владелец", role: "owner" }),
      member({ blocked: true, block_reason: "увольнение" }),
    ]);
    unblockMember.mockResolvedValue(member());
    await show();
    fireEvent.click(screen.getByTitle(/Вернуть доступ/));
    await waitFor(() => expect(unblockMember).toHaveBeenCalledWith("o1", "u2"));
  });

  it("отказ сервера показывается его же словами", async () => {
    // «Нельзя приостановить владельца» — граница безопасности, и своя формулировка
    // разошлась бы с правилом на бэкенде.
    blockMember.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409, data: { detail: "Нельзя приостановить себя" } },
    });
    await show();
    fireEvent.click(screen.getByTitle("Приостановить доступ"));
    fireEvent.change(screen.getByLabelText("Причина приостановки"),
                     { target: { value: "ошибка" } });
    fireEvent.click(screen.getByText("Приостановить"));
    await waitFor(() => expect(toast)
      .toHaveBeenCalledWith("Нельзя приостановить себя", { kind: "error" }));
  });

  /** Видимость активности (A3): кто пользуется организацией и кто молчит. */

  it("«не заходил» показывается словами, а не датой месячной давности", async () => {
    const today = new Date().toISOString();
    getMembers.mockResolvedValue([
      member({ user_id: "u1", email: "own@e.ru", full_name: "Владелец", role: "owner",
               last_seen_at: today }),
      member({ last_seen_at: null }),
    ]);
    await show();
    expect(screen.getByText("сегодня")).toBeTruthy();
    // Пустая отметка — «нет данных», а не «никогда»: до её появления присутствие не
    // писалось, и выдавать молчание за отсутствие было бы враньём о живом человеке.
    expect(screen.getByText("нет данных")).toBeTruthy();
  });

  it("молчащий дольше месяца помечен как кандидат на отзыв доступа", async () => {
    const long = new Date(Date.now() - 45 * 86_400_000).toISOString();
    getMembers.mockResolvedValue([
      member({ user_id: "u1", email: "own@e.ru", full_name: "Владелец", role: "owner" }),
      member({ last_seen_at: long }),
    ]);
    await show();
    expect(screen.getByText("не активен")).toBeTruthy();
  });

  it("«действия участника» ведут в журнал с отбором по нему", async () => {
    // Второго списка действий рядом не заводим: два источника одних событий разошлись
    // бы, и пришлось бы гадать, какой из них правда.
    const onShowActions = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })}>
        <MembersTab orgId="o1" myRole="owner" myUserId="u1"
                    onShowActions={onShowActions} />
      </QueryClientProvider>,
    );
    await screen.findByText("Коллега");
    // Кнопка есть у каждого участника — берём строку коллеги.
    fireEvent.click(screen.getByTitle("Действия участника: Коллега"));
    expect(onShowActions).toHaveBeenCalledWith("k@e.ru");
  });

  it("без права на управление организацией ссылки на журнал нет", async () => {
    await show("editor");
    expect(screen.queryByTitle(/Действия участника/)).toBeNull();
  });
});
