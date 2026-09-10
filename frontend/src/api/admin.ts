import { api } from "./client";
import type { Schema } from "./gen";

/**
 * Служебный контур платформы (ADMIN-DECOMPOSITION.md, B1).
 *
 * Раздел видит только сотрудник платформы. Признак `is_staff` приходит в профиле и
 * управляет **показом** раздела — права проверяет сервер на каждом запросе: интерфейс,
 * который «разрешает», защищает ровно до первого прямого обращения к API.
 *
 * Здесь нет ни одного запроса за содержимым моделей клиентов: оператор видит клиента
 * снаружи (кто, с какого числа, за что платит, сколько чего завёл). Так же устроен и
 * сервер — не потому, что фронт «просто не спрашивает».
 */

export type StaffOrg = Schema<"StaffOrgOut">;
export type StaffOrgDetail = Schema<"StaffOrgDetail">;
export type StaffOrgPage = Schema<"StaffOrgPage">;
export type StaffUser = Schema<"StaffUserOut">;
export type StaffLogEntry = Schema<"StaffLogEntryOut">;
export type StaffLogPage = Schema<"StaffLogPage">;
export type AuditLogPage = Schema<"AuditLogPage">;

export async function getStaffOrganizations(q = "", limit = 50): Promise<StaffOrgPage> {
  const { data } = await api.get<StaffOrgPage>("/api/v1/admin/organizations",
    { params: { q, limit } });
  return data;
}

/**
 * Карточка клиента. Запрос **пишется в журнал самой организации**: клиент обязан видеть,
 * что к нему приходили. Открывать её «просто посмотреть» — то же самое, что зайти.
 */
export async function getStaffOrganization(orgId: string): Promise<StaffOrgDetail> {
  const { data } = await api.get<StaffOrgDetail>(`/api/v1/admin/organizations/${orgId}`);
  return data;
}

/** Журнал клиента — тот же, что видит его администратор (второго представления нет). */
export async function getStaffOrgLog(orgId: string, limit = 100): Promise<AuditLogPage> {
  const { data } = await api.get<AuditLogPage>(
    `/api/v1/admin/organizations/${orgId}/audit-log`, { params: { limit } });
  return data;
}

export async function searchStaffUsers(q = "", limit = 50): Promise<StaffUser[]> {
  const { data } = await api.get<StaffUser[]>("/api/v1/admin/users", { params: { q, limit } });
  return data;
}

/** Служебный журнал: где были наши сотрудники. Только чтение — как и журнал клиента. */
export async function getStaffLog(limit = 100): Promise<StaffLogPage> {
  const { data } = await api.get<StaffLogPage>("/api/v1/admin/log", { params: { limit } });
  return data;
}
