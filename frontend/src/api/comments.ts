import { api } from "./client";
import type { Schema } from "./gen";

/**
 * Обсуждение рядом с числами (D3).
 *
 * Один клиент на оба продукта: у проекта и у дела обсуждение устроено одинаково, и
 * вторая копия этих вызовов разошлась бы с первой. Различается только адрес сущности.
 *
 * `anchor` — место внутри сущности (вкладка, строка отчёта), `anchorLabel` — его подпись
 * **на момент написания**: объект переименуют или удалят, а разговор обязан остаться
 * понятным, поэтому подпись уходит на сервер вместе с репликой.
 */
export type Comment = Schema<"CommentOut">;
export type CommentCreated = Schema<"CommentCreated">;

export type Subject = { kind: "project" | "case"; id: string };

const base = (s: Subject) =>
  s.kind === "project" ? `/api/v1/projects/${s.id}` : `/api/v1/audit/subjects/${s.id}`;

export async function getComments(s: Subject, anchor?: string): Promise<Comment[]> {
  const { data } = await api.get<Comment[]>(`${base(s)}/comments`, {
    params: anchor ? { anchor } : undefined,
  });
  return data;
}

export async function addComment(s: Subject, body: string, anchor = "",
                                 anchorLabel = ""): Promise<CommentCreated> {
  const { data } = await api.post<CommentCreated>(`${base(s)}/comments`, {
    body, anchor, anchor_label: anchorLabel,
  });
  return data;
}

/** Закрыть обсуждение (вопрос снят) или открыть заново. */
export async function resolveComment(id: string, resolved: boolean): Promise<Comment> {
  const { data } = resolved
    ? await api.post<Comment>(`/api/v1/comments/${id}/resolve`)
    : await api.delete<Comment>(`/api/v1/comments/${id}/resolve`);
  return data;
}

/** Удалить реплику. Текст стирается, «надгробие» остаётся: на реплику могли ответить. */
export async function deleteComment(id: string): Promise<Comment> {
  const { data } = await api.delete<Comment>(`/api/v1/comments/${id}`);
  return data;
}

/**
 * Письма об обсуждении (OPEN-DECISIONS §5).
 *
 * Подписан тот, кто участвует: написал реплику или был упомянут. Хранится и правится
 * только исключение — «не писать мне об этой ветке»; смысл отписки приходит с сервера
 * (`note`), потому что вторая формулировка на клиенте однажды разошлась бы с тем, что
 * платформа делает на самом деле.
 */
export type ThreadSubscription = Schema<"ThreadSubscriptionOut">;

export async function getThreadSubscription(s: Subject, anchor = "")
    : Promise<ThreadSubscription> {
  const { data } = await api.get<ThreadSubscription>("/api/v1/comments/subscription", {
    params: { subject_type: s.kind, subject_id: s.id, anchor },
  });
  return data;
}

export async function setThreadSubscription(s: Subject, anchor: string, muted: boolean)
    : Promise<ThreadSubscription> {
  const { data } = await api.post<ThreadSubscription>("/api/v1/comments/subscription", {
    subject_type: s.kind, subject_id: s.id, anchor, muted,
  });
  return data;
}

/** Отписка по ссылке из письма — **без входа**: токен уже доказал, кто это. */
export async function unsubscribeByToken(token: string, muted = true)
    : Promise<ThreadSubscription> {
  const { data } = await api.post<ThreadSubscription>("/api/v1/comments/unsubscribe",
                                                      { token, muted });
  return data;
}
