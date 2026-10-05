import { api } from "./client";
import type { Schema } from "./gen";
import type { User } from "./types";

// Публичные документы и согласие на обработку ПД (пакет L, L5) — из OpenAPI-схемы.
export type LegalIndex = Schema<"LegalIndexOut">;
export type LegalDoc = Schema<"LegalDocOut">;

/** Документы, которые есть у платформы, — в порядке показа в подвале и на странице. */
export const LEGAL_SLUGS = ["offer", "privacy", "consent", "requisites"] as const;
export type LegalSlug = (typeof LEGAL_SLUGS)[number];

export async function getLegalIndex(): Promise<LegalIndex> {
  const { data } = await api.get<LegalIndex>("/api/v1/legal");
  return data;
}

export async function getLegalDoc(slug: string): Promise<LegalDoc> {
  const { data } = await api.get<LegalDoc>(`/api/v1/legal/${encodeURIComponent(slug)}`);
  return data;
}

/** Дать согласие на обработку ПД из профиля — для учётных записей, заведённых до L5. */
export async function givePdConsent(): Promise<User> {
  const { data } = await api.post<User>("/api/v1/auth/pd-consent");
  return data;
}

/**
 * Вид ссылки активации — приглашение или сброс пароля — **для подписи экрана**, а не для
 * доступа: токен подписан, и проверяет его сервер. Приглашённому нужна отметка согласия
 * на обработку ПД, сбросу — нет. Нечитаемый токен считается приглашением: лишний раз
 * спросить согласие безопаснее, чем не спросить.
 */
export function activationKind(token: string): "invite" | "reset" {
  try {
    const part = token.split(".")[1] ?? "";
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/").padEnd(
      Math.ceil(part.length / 4) * 4, "="));
    return (JSON.parse(json) as { typ?: string }).typ === "reset" ? "reset" : "invite";
  } catch {
    return "invite";
  }
}
