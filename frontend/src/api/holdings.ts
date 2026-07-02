import type { CalcResponse } from "./calc";
import { api } from "./client";

export interface HoldingMember {
  project_id: string;
  role: string; // "parent" | "subsidiary"
}

export interface Holding {
  id: string;
  name: string;
  created_at: string;
  members: HoldingMember[];
}

export const HOLDING_ROLES: [string, string][] = [
  ["parent", "Головная"],
  ["subsidiary", "Дочерняя"],
];

export async function listHoldings(): Promise<Holding[]> {
  const { data } = await api.get<Holding[]>("/api/v1/holdings");
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

export async function consolidateHolding(id: string): Promise<CalcResponse> {
  const { data } = await api.post<CalcResponse>(`/api/v1/holdings/${id}/consolidate`);
  return data;
}
