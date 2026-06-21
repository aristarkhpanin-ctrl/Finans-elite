import { api } from "./client";
import type {
  LoginPayload,
  OrganizationMembership,
  RegisterPayload,
  TokenResponse,
  User,
} from "./types";

export async function register(payload: RegisterPayload): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/api/v1/auth/register", payload);
  return data;
}

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/api/v1/auth/login", payload);
  return data;
}

export async function getMe(): Promise<User> {
  const { data } = await api.get<User>("/api/v1/auth/me");
  return data;
}

export async function getMyOrganizations(): Promise<OrganizationMembership[]> {
  const { data } = await api.get<OrganizationMembership[]>("/api/v1/organizations");
  return data;
}
