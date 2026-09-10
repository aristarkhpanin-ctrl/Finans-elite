// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Comment } from "../api/comments";
import { Comments } from "./Comments";

/**
 * Обсуждение рядом с числами (D3). Проверяется то, ради чего панель и сделана: реплика
 * несёт **место**, упоминание не выдаётся за право доступа, нераспознанное упоминание
 * названо вслух, а удалённая реплика говорит о себе вместо того, чтобы исчезнуть.
 */

const getComments = vi.fn();
const addComment = vi.fn();
const resolveComment = vi.fn();
const deleteComment = vi.fn();
vi.mock("../api/comments", async (orig) => ({
  ...(await orig<typeof import("../api/comments")>()),
  getComments: (...a: unknown[]) => getComments(...a),
  addComment: (...a: unknown[]) => addComment(...a),
  resolveComment: (...a: unknown[]) => resolveComment(...a),
  deleteComment: (...a: unknown[]) => deleteComment(...a),
}));

const toast = vi.fn();
vi.mock("./Toast", () => ({ useToast: () => toast }));
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", email: "o@e.ru", full_name: "Владелец" } }),
}));

const row = (over: Partial<Comment> = {}): Comment => ({
  id: "c1", subject_type: "project", subject_id: "p1",
  anchor: "report:income", anchor_label: "Прибыли и убытки",
  author_email: "o@e.ru", author_name: "Владелец",
  body: "Откуда такая себестоимость?", mentions: [],
  created_at: "2026-09-10T10:00:00Z",
  resolved: false, resolved_at: null, resolved_by: "", deleted: false, ...over,
} as Comment);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getComments.mockResolvedValue([row()]);
  addComment.mockResolvedValue({
    comment: row({ id: "c2", body: "новая" }), notified: [], unknown_mentions: [],
    mail: { attempted: false, ok: false, error: "" },
  });
  resolveComment.mockResolvedValue(row({ resolved: true, resolved_by: "o@e.ru" }));
  deleteComment.mockResolvedValue(row({ deleted: true, body: "Реплика удалена автором." }));
});

function show(props: Partial<Parameters<typeof Comments>[0]> = {}) {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <Comments subject={{ kind: "project", id: "p1" }} anchor="report:income"
                anchorLabel="Прибыли и убытки" {...props} />
    </QueryClientProvider>,
  );
}

it("показывает место, к которому привязано обсуждение", async () => {
  // «Обсуждение проекта» без места — чат, из которого через месяц не понять, о какой
  // строке шла речь.
  show();
  expect(await screen.findByText("Откуда такая себестоимость?")).toBeTruthy();
  expect(screen.getAllByText("Прибыли и убытки").length).toBeGreaterThan(0);
});

it("реплика уходит вместе с местом и его подписью", async () => {
  show();
  await screen.findByText("Откуда такая себестоимость?");
  fireEvent.change(screen.getByLabelText("Новая реплика"),
                   { target: { value: "Проверил, всё верно" } });
  fireEvent.click(screen.getByRole("button", { name: "Отправить" }));

  await waitFor(() => expect(addComment).toHaveBeenCalledWith(
    { kind: "project", id: "p1" }, "Проверил, всё верно", "report:income",
    "Прибыли и убытки"));
});

it("не обещает, что упоминание открывает доступ", async () => {
  show();
  expect(await screen.findByText(/прав на проект не даёт/)).toBeTruthy();
});

it("нераспознанное упоминание названо вслух", async () => {
  // «Позвал, и никто не пришёл» — худший вид тишины.
  addComment.mockResolvedValue({
    comment: row(), notified: [], unknown_mentions: ["nobody@else.ru"],
    mail: { attempted: false, ok: false, error: "" },
  });
  show();
  await screen.findByText("Откуда такая себестоимость?");
  fireEvent.change(screen.getByLabelText("Новая реплика"),
                   { target: { value: "@nobody@else.ru глянь" } });
  fireEvent.click(screen.getByRole("button", { name: "Отправить" }));

  await waitFor(() => expect(toast).toHaveBeenCalledWith(
    expect.stringContaining("В организации нет: nobody@else.ru"), { kind: "error" }));
});

it("без почты не делает вид, что коллеге ушло письмо", async () => {
  addComment.mockResolvedValue({
    comment: row(), notified: ["k@e.ru"], unknown_mentions: [],
    mail: { attempted: false, ok: false, error: "" },
  });
  show();
  await screen.findByText("Откуда такая себестоимость?");
  fireEvent.change(screen.getByLabelText("Новая реплика"),
                   { target: { value: "@k@e.ru глянь" } });
  fireEvent.click(screen.getByRole("button", { name: "Отправить" }));

  await waitFor(() => expect(toast).toHaveBeenCalledWith(
    expect.stringContaining("Писем платформа не отправляет"), { kind: "success" }));
});

it("закрытое обсуждение называет закрывшего", async () => {
  // «Вопрос снят» без имени снявшего — это не ответ, а тишина.
  getComments.mockResolvedValue([row({ resolved: true, resolved_by: "k@e.ru" })]);
  show();
  expect(await screen.findByText(/закрыл k@e.ru/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Открыть заново" })).toBeTruthy();
});

it("удалённая реплика говорит о себе, а не исчезает", async () => {
  getComments.mockResolvedValue([row({ deleted: true, body: "Реплика удалена автором." })]);
  show();
  // На неё уже могли ответить: пропавшая без следа строка читается как не сказанная.
  expect(await screen.findByText("Реплика удалена автором.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Удалить" })).toBeNull();
});

it("чужую реплику удалить не предлагает", async () => {
  getComments.mockResolvedValue([row({ author_email: "k@e.ru", author_name: "Коллега" })]);
  show();
  await screen.findByText("Коллега");
  expect(screen.queryByRole("button", { name: "Удалить" })).toBeNull();
});

it("пустое обсуждение зовёт спросить рядом с числами", async () => {
  getComments.mockResolvedValue([]);
  show();
  expect(await screen.findByText(/рядом с числами/)).toBeTruthy();
});
