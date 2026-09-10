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

/**
 * Что умеет **эта установка** платформы (D1).
 *
 * Отправка писем включается на месте, и экран входа обязан узнать о ней с сервера:
 * «Забыли пароль?», нарисованная там, где письма не уходят, ведёт человека в тупик — а
 * тупик, который выглядит как выход, хуже честно названного его отсутствия.
 */
export type Capabilities = Schema<"CapabilitiesOut">;

export async function getCapabilities(): Promise<Capabilities> {
  const { data } = await api.get<Capabilities>("/api/v1/auth/capabilities");
  return data;
}

/**
 * «Забыли пароль»: попросить ссылку на почту. Ответ **один и тот же** для любого
 * адреса — существующего, чужого, выдуманного: иначе форма превращается в проверялку
 * «есть ли у вас такой клиент». Показываем именно его, своего текста не сочиняем.
 */
export async function requestPasswordReset(email: string): Promise<string> {
  const { data } = await api.post<{ message: string }>(
    "/api/v1/auth/forgot-password", { email });
  return data.message;
}

/**
 * Требования к паролю — **с сервера**, а не своим текстом на каждом экране (C2).
 *
 * Перечисленные в интерфейсе отдельно, они однажды разойдутся с проверкой, и человек
 * прочтёт одно, а получит другое. `leak_check` говорит, включена ли сейчас проверка по
 * базе утечек: обещать её при выключенной значило бы утверждать, что платформа делает
 * то, чего не делает.
 */
export type PasswordPolicy = Schema<"PasswordPolicyOut">;

export async function getPasswordPolicy(): Promise<PasswordPolicy> {
  const { data } = await api.get<PasswordPolicy>("/api/v1/auth/password-policy");
  return data;
}

/**
 * Второй фактор: одноразовые коды из приложения (C2).
 *
 * Настройка идёт в два шага и включается **только** после подтверждения кодом: иначе
 * опечатки в приложении хватило бы, чтобы остаться снаружи своей учётной записи.
 * Резервные коды показываются один раз — почты у платформы нет, и письма «восстановите
 * доступ» не будет.
 */
export type TotpStatus = Schema<"TotpStatusOut">;
export type TotpSetup = Schema<"TotpSetupOut">;

export async function getTotpStatus(): Promise<TotpStatus> {
  const { data } = await api.get<TotpStatus>("/api/v1/auth/totp");
  return data;
}

export async function startTotpSetup(): Promise<TotpSetup> {
  const { data } = await api.post<TotpSetup>("/api/v1/auth/totp/setup");
  return data;
}

/** Подтвердить настройку кодом → резервные коды (показываются один раз). */
export async function enableTotp(code: string): Promise<string[]> {
  const { data } = await api.post<{ codes: string[] }>("/api/v1/auth/totp/enable", { code });
  return data.codes;
}

/** Перевыпустить резервные коды. Прежние перестают работать сразу. */
export async function reissueRecoveryCodes(password: string): Promise<string[]> {
  const { data } = await api.post<{ codes: string[] }>(
    "/api/v1/auth/totp/recovery-codes", { password });
  return data.codes;
}

/** Выключить второй фактор — по паролю: сессию могли украсть, пароль знает владелец. */
export async function disableTotp(password: string): Promise<void> {
  await api.post("/api/v1/auth/totp/disable", { password });
}

/**
 * Свои данные: выгрузка и удаление учётной записи (C3, 152-ФЗ).
 *
 * Выгрузка — файл о **человеке**, а не о компании: проектов и дел в нём нет, и он сам
 * говорит, почему. Скачивание идёт через blob, а не ссылкой на адрес: запрос требует
 * заголовка сессии, и открытая в новой вкладке ссылка ушла бы без него.
 */
export async function downloadMyData(): Promise<void> {
  const { data } = await api.get("/api/v1/auth/export", { responseType: "blob" });
  const url = URL.createObjectURL(data as Blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "my-data.json";
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Что случится при удалении — **до** нажатия: какие организации исчезнут вместе с
 * учётной записью, из каких человек просто выйдет, что останется и что мешает.
 */
export type DeletionPlan = Schema<"DeletionPlanOut">;

export async function getDeletionPlan(): Promise<DeletionPlan> {
  const { data } = await api.get<DeletionPlan>("/api/v1/auth/delete-preview");
  return data;
}

/** Удалить свою учётную запись — по паролю. Необратимо. */
export async function deleteMyAccount(password: string): Promise<DeletionPlan> {
  const { data } = await api.post<DeletionPlan>("/api/v1/auth/delete", { password });
  return data;
}
