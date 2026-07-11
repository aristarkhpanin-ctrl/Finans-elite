import axios from "axios";
import { api } from "./client";
import type { Schema } from "./gen";

// Ответы — из сгенерированной OpenAPI-схемы (Ф10, ревью плана).
export type Finding = Schema<"FindingOut">;
export type ReviewResponse = Schema<"ReviewResponse">;
export type FinalizeResponse = Schema<"FinalizeResponse">;

export type Severity = "risk" | "warning" | "info";
export type Light = "ok" | Severity;

/** Ревью плана: находки/рекомендации по итогам расчёта. deep — со стохастикой (divergence). */
export async function getReview(id: string, deep = false): Promise<ReviewResponse> {
  const { data } = await api.get<ReviewResponse>(`/api/v1/projects/${id}/review`, {
    params: { deep },
  });
  return data;
}

/** Финализировать план (гейт ревью). acknowledge=true подтверждает осознание risk-находок. */
export async function finalizeProject(id: string, acknowledge: boolean): Promise<FinalizeResponse> {
  const { data } = await api.post<FinalizeResponse>(`/api/v1/projects/${id}/finalize`, {
    acknowledge,
  });
  return data;
}

/** Ревью из тела 409 (гейт не пройден): backend кладёт его в detail.review. */
export function finalizeBlockReview(e: unknown): ReviewResponse | undefined {
  if (axios.isAxiosError(e) && e.response?.status === 409) {
    const detail = e.response.data?.detail as { review?: ReviewResponse } | undefined;
    if (detail && typeof detail === "object" && detail.review) return detail.review;
  }
  return undefined;
}
