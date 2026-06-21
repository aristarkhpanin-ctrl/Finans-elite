import { api } from "./client";

export const ROLES: [string, string][] = [
  ["owner", "Владелец"],
  ["admin", "Администратор"],
  ["editor", "Редактор"],
  ["analyst", "Аналитик"],
  ["viewer", "Наблюдатель"],
];

export const roleLabel = (role: string) => ROLES.find(([k]) => k === role)?.[1] ?? role;

export interface Member {
  user_id: string;
  email: string;
  full_name: string;
  role: string;
}

export interface Plan {
  code: string;
  name: string;
  price_rub: number;
  max_projects: number | null;
  max_members: number | null;
}

export interface Subscription {
  plan_code: string;
  plan_name: string;
  status: string;
  current_period_end: string | null;
  max_projects: number | null;
  max_members: number | null;
  used_projects: number;
  used_members: number;
}

export interface CheckoutResponse {
  activated: boolean;
  payment_id: string | null;
  confirmation_url: string | null;
}

export async function getMembers(orgId: string): Promise<Member[]> {
  const { data } = await api.get<Member[]>(`/api/v1/organizations/${orgId}/members`);
  return data;
}

export async function addMember(orgId: string, body: { email: string; full_name: string; role: string }): Promise<Member> {
  const { data } = await api.post<Member>(`/api/v1/organizations/${orgId}/members`, body);
  return data;
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
