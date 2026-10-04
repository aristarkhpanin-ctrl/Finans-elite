import { api } from "./client";
import type { Schema } from "./gen";

// Ссылка для инвестора или банка (пакет L, L4) — типы из OpenAPI-схемы.
export type ShareLink = Schema<"ShareLinkOut">;
export type ShareLinks = Schema<"ShareLinksOut">;
export type ShareLinkCreated = Schema<"ShareLinkCreated">;
export type SharedPlan = Schema<"SharedPlanOut">;

export interface ShareLinkRequest {
  /** Для кого ссылка: имя печатается на копии. */
  label: string;
  /** Срок в днях; дольше предела сервер не откроет и скажет об этом. */
  days: number;
  /** Какую версию открыть; не задана — снимок делается сейчас. */
  version_id?: string | null;
}

export async function listShareLinks(projectId: string): Promise<ShareLinks> {
  const { data } = await api.get<ShareLinks>(`/api/v1/projects/${projectId}/share-links`);
  return data;
}

export async function createShareLink(projectId: string,
                                      body: ShareLinkRequest): Promise<ShareLinkCreated> {
  const { data } = await api.post<ShareLinkCreated>(
    `/api/v1/projects/${projectId}/share-links`, body);
  return data;
}

export async function revokeShareLink(projectId: string, linkId: string): Promise<void> {
  await api.delete(`/api/v1/projects/${projectId}/share-links/${linkId}`);
}

/** План по ссылке — **без входа**: секрет в адресе и есть пропуск. */
export async function getSharedPlan(token: string): Promise<SharedPlan> {
  const { data } = await api.get<SharedPlan>(`/api/v1/shared/${encodeURIComponent(token)}`);
  return data;
}

/** Полный адрес страницы просмотра — его отправитель передаёт инвестору или банку. */
export function shareUrl(path: string): string {
  return `${window.location.origin}${path}`;
}
