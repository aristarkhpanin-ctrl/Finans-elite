import type { CalcResponse } from "./calc";
import { api } from "./client";

export interface HoldingMember {
  project_id: string;
  role: string; // "parent" | "subsidiary"
}

export interface HoldingConsolidation {
  npv: string;
  rate: string;
  at: string;
}

export interface Holding {
  id: string;
  name: string;
  created_at: string;
  members: HoldingMember[];
  last_consolidation: HoldingConsolidation | null;
}

/** Вклад проекта в консолидацию (B3). */
export interface PerProject {
  project_id: string;
  name: string;
  role: string;
  npv: string;
  irr_annual: string | null;
  revenue_total: string;
  net_profit_total: string;
}

export interface ConsolidateResponse extends CalcResponse {
  per_project: PerProject[];
}

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
