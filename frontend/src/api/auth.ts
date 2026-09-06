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

/**
 * Активация приглашения: по ссылке завести пароль и войти.
 *
 * Токен приглашения — не токен входа: им можно только задать пароль, и только один
 * раз. Проверяет это бэкенд, здесь важно другое — сюда попадают **до** авторизации,
 * поэтому запрос идёт без заголовка сессии.
 */
export async function activateInvite(payload: {
  token: string; password: string; full_name?: string;
}): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/api/v1/auth/activate", payload);
  return data;
}

export async function updateProfile(full_name: string): Promise<User> {
  const { data } = await api.patch<User>("/api/v1/auth/me", { full_name });
  return data;
}

export async function changePassword(current_password: string,
                                     new_password: string): Promise<void> {
  await api.post("/api/v1/auth/password", { current_password, new_password });
}
