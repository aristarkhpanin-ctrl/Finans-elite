import { api } from "./client";
import type { Schema } from "./gen";
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

/**
 * Действующие входы в свою учётную запись (C1).
 *
 * Устройство и адрес приходят от самого клиента и подделываются кем угодно: это
 * подсказка владельцу («это точно был я?»), а не удостоверение устройства — и на экране
 * это сказано, чтобы список не читался как доказательство.
 */
export type SessionRow = Schema<"SessionOut">;

export async function getSessions(): Promise<SessionRow[]> {
  const { data } = await api.get<SessionRow[]>("/api/v1/auth/sessions");
  return data;
}

/** Закрыть конкретный вход. Отзыв мгновенный: сеанс читается из базы на каждом запросе. */
export async function revokeSession(id: string): Promise<void> {
  await api.delete(`/api/v1/auth/sessions/${id}`);
}

/**
 * «Выйти на всех устройствах» — включая текущее. Возвращает, сколько входов закрыто:
 * человеку говорят, что именно с ним произошло, а не безличное «готово».
 */
export async function revokeAllSessions(): Promise<number> {
  const { data } = await api.post<{ closed: number }>("/api/v1/auth/sessions/revoke-all");
  return data.closed;
}
