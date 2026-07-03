import { api } from "./client";
import type { Schema } from "./gen";

// Типы ответов — из сгенерированной OpenAPI-схемы (см. gen.ts).
export type HoldingMember = Schema<"HoldingMemberOut">;
export type HoldingConsolidation = Schema<"HoldingConsolidationOut">;
export type Holding = Schema<"HoldingOut">;
/** Вклад проекта в консолидацию (B3). */
export type PerProject = Schema<"PerProjectOut">;
export type ConsolidateResponse = Schema<"ConsolidateResponse">;

export const HOLDING_ROLES: [string, string][] = [
  ["parent", "Головная"],
  ["subsidiary", "Дочерняя"],
];

export async function listHoldings(): Promise<Holding[]> {
  const { data } = await api.get<Holding[]>("/api/v1/holdings");
  return data;
}

export async function getHolding(id: string): Promise<Holding> {
  const { data } = await api.get<Holding>(`/api/v1/holdings/${id}`);
  return data;
}

export async function createHolding(name: string): Promise<Holding> {
  const { data } = await api.post<Holding>("/api/v1/holdings", { name });
  return data;
}

export async function deleteHolding(id: string): Promise<void> {
  await api.delete(`/api/v1/holdings/${id}`);
}

export async function addHoldingMember(id: string, projectId: string, role: string): Promise<Holding> {
  const { data } = await api.post<Holding>(`/api/v1/holdings/${id}/members`, {
    project_id: projectId,
    role,
  });
  return data;
}

export async function patchHoldingMember(id: string, projectId: string, role: string): Promise<Holding> {
  const { data } = await api.patch<Holding>(`/api/v1/holdings/${id}/members/${projectId}`, { role });
  return data;
}

export async function removeHoldingMember(id: string, projectId: string): Promise<void> {
  await api.delete(`/api/v1/holdings/${id}/members/${projectId}`);
}

export async function consolidateHolding(id: string, groupDiscountRate?: string): Promise<ConsolidateResponse> {
  const { data } = await api.post<ConsolidateResponse>(`/api/v1/holdings/${id}/consolidate`, null, {
    params: groupDiscountRate ? { group_discount_rate: groupDiscountRate } : undefined,
  });
  return data;
}
