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

/**
 * Приостановить организацию (B2). **Не конфискация данных**: клиент продолжает видеть,
 * считать и выгружать свои модели — закрыты только правки. Причина обязательна и
 * показывается самой организации; оплата приостановку не снимает.
 */
export async function suspendOrganization(orgId: string, reason: string): Promise<StaffOrgDetail> {
  const { data } = await api.post<StaffOrgDetail>(
    `/api/v1/admin/organizations/${orgId}/suspend`, { reason });
  return data;
}

export async function resumeOrganization(orgId: string): Promise<StaffOrgDetail> {
  const { data } = await api.delete<StaffOrgDetail>(
    `/api/v1/admin/organizations/${orgId}/suspend`);
  return data;
}

/**
 * Заблокировать учётную запись платформы — сразу во всех организациях (B2).
 *
 * Не путать с приостановкой членства (A1): та закрывает человеку одно рабочее
 * пространство и делается его же администратором. Эта — про саму учётную запись,
 * поэтому право только у платформы.
 */
export async function blockUser(userId: string, reason: string): Promise<StaffUser> {
  const { data } = await api.post<StaffUser>(`/api/v1/admin/users/${userId}/block`, { reason });
  return data;
}

export async function unblockUser(userId: string): Promise<StaffUser> {
  const { data } = await api.delete<StaffUser>(`/api/v1/admin/users/${userId}/block`);
  return data;
}

export type PlatformMetrics = Schema<"PlatformMetricsOut">;

/**
 * Сводка платформы (B3). Числа собираются из уже имеющихся данных — второй системы
 * учёта под метрики не заводится.
 *
 * Ответ несёт `notes` — **чего эти числа не значат**. Показывать их обязательно: ноль за
 * период, которого журнал не застал, выглядит ровно как ноль событий.
 */
export async function getPlatformMetrics(days = 30, months = 12): Promise<PlatformMetrics> {
  const { data } = await api.get<PlatformMetrics>("/api/v1/admin/metrics",
    { params: { days, months } });
  return data;
}

/** Выгрузка сводки: те же числа и те же оговорки — таблица без них утверждает больше. */
export async function downloadMetricsCsv(days = 30, months = 12): Promise<void> {
  const { data } = await api.get<Blob>("/api/v1/admin/metrics.csv",
    { params: { days, months }, responseType: "blob" });
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = "сводка-платформы.csv";
  a.click();
  URL.revokeObjectURL(url);
}
