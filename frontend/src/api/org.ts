import { api } from "./client";
import type { Schema } from "./gen";

export const ROLES: [string, string][] = [
  ["owner", "Владелец"],
  ["admin", "Администратор"],
  ["editor", "Редактор"],
  ["analyst", "Аналитик"],
  ["viewer", "Наблюдатель"],
];

export const roleLabel = (role: string) => ROLES.find(([k]) => k === role)?.[1] ?? role;

// Типы ответов — из сгенерированной OpenAPI-схемы (см. gen.ts).
export type Member = Schema<"MemberOut">;
export type Plan = Schema<"PlanOut">;
export type Subscription = Schema<"SubscriptionOut">;
export type CheckoutResponse = Schema<"CheckoutResponse">;

export async function createOrganization(name: string): Promise<{ id: string; name: string }> {
  const { data } = await api.post<{ id: string; name: string }>("/api/v1/organizations", { name });
  return data;
}

export async function getMembers(orgId: string): Promise<Member[]> {
  const { data } = await api.get<Member[]>(`/api/v1/organizations/${orgId}/members`);
  return data;
}

export async function addMember(orgId: string, body: { email: string; full_name: string; role: string }): Promise<Member> {
  const { data } = await api.post<Member>(`/api/v1/organizations/${orgId}/members`, body);
  return data;
}

export async function patchMemberRole(orgId: string, userId: string, role: string): Promise<Member> {
  const { data } = await api.patch<Member>(`/api/v1/organizations/${orgId}/members/${userId}`, { role });
  return data;
}

export async function removeMember(orgId: string, userId: string): Promise<void> {
  await api.delete(`/api/v1/organizations/${orgId}/members/${userId}`);
}

export async function getPlans(): Promise<Plan[]> {
  const { data } = await api.get<Plan[]>("/api/v1/plans");
  return data;
}

export async function getSubscription(orgId: string): Promise<Subscription> {
  const { data } = await api.get<Subscription>(`/api/v1/organizations/${orgId}/subscription`);
  return data;
}

export async function checkout(orgId: string, planCode: string): Promise<CheckoutResponse> {
  const { data } = await api.post<CheckoutResponse>(`/api/v1/organizations/${orgId}/billing/checkout`, {
    plan_code: planCode,
    return_url: window.location.origin + "/organization",
  });
  return data;
}
