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
export type AuditLogEntry = Schema<"AuditLogEntryOut">;
export type AuditLogPage = Schema<"AuditLogPage">;

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

/** Одноразовая ссылка входа: `invite` — пароля ещё нет, `reset` — пароль забыт. */
export type AccessLink = Schema<"AccessLinkOut">;

/**
 * Выдать участнику ссылку входа. Единственный путь восстановления пароля в продукте:
 * почтовой отправки нет, поэтому ссылку передаёт администратор лично — как и
 * приглашение. Владельцу и участнику нескольких организаций сервер откажет и назовёт
 * причину (это не ошибка интерфейса, а граница безопасности).
 */
export async function issueAccessLink(orgId: string, userId: string): Promise<AccessLink> {
  const { data } = await api.post<AccessLink>(
    `/api/v1/organizations/${orgId}/members/${userId}/access-link`);
  return data;
}

/**
 * Приостановить доступ участника в этой организации (A1).
 *
 * **Приостановка — не удаление.** Участник остаётся в списке со своей ролью: удаление
 * стирает связь, и вернуть его можно только заведением заново. Отзыв мгновенный —
 * права проверяются по базе на каждом запросе, поэтому выданный токен не спасает.
 * Блокируется членство, а не учётная запись: в других организациях человек работает.
 */
export async function blockMember(orgId: string, userId: string, reason: string): Promise<Member> {
  const { data } = await api.post<Member>(
    `/api/v1/organizations/${orgId}/members/${userId}/block`, { reason });
  return data;
}

/** Вернуть доступ. Причина стирается, след в журнале остаётся — журнал и есть память. */
export async function unblockMember(orgId: string, userId: string): Promise<Member> {
  const { data } = await api.delete<Member>(
    `/api/v1/organizations/${orgId}/members/${userId}/block`);
  return data;
}

export async function patchMemberRole(orgId: string, userId: string, role: string): Promise<Member> {
  const { data } = await api.patch<Member>(`/api/v1/organizations/${orgId}/members/${userId}`, { role });
  return data;
}

export async function removeMember(orgId: string, userId: string): Promise<void> {
  await api.delete(`/api/v1/organizations/${orgId}/members/${userId}`);
}

/** Каталог тарифов продукта: у «Элит» и «Аудита» он свой — они продаются порознь. */
export async function getPlans(product?: string): Promise<Plan[]> {
  const { data } = await api.get<Plan[]>("/api/v1/plans", { params: { product } });
  return data;
}

export async function getSubscription(orgId: string, product = "business"): Promise<Subscription> {
  const { data } = await api.get<Subscription>(
    `/api/v1/organizations/${orgId}/subscription`, { params: { product } });
  return data;
}

export async function checkout(orgId: string, planCode: string): Promise<CheckoutResponse> {
  const { data } = await api.post<CheckoutResponse>(`/api/v1/organizations/${orgId}/billing/checkout`, {
    plan_code: planCode,
    return_url: window.location.origin + "/organization",
  });
  return data;
}

/** Строка справочника отраслевых ориентиров организации (SPEC, Прил. Ф). */
export type Benchmark = Schema<"BenchmarkOut">;
export type BenchmarkIn = Schema<"BenchmarkIn">;

/** Базы мультипликатора: сравнение возможно только при совпадении базы. */
export const BENCHMARK_METRICS: [BenchmarkIn["metric"], string][] = [
  ["ev_ebitda", "EV / EBITDA"],
  ["ev_ebit", "EV / EBIT"],
  ["ev_revenue", "EV / Выручка"],
];

export async function getBenchmarks(orgId: string): Promise<Benchmark[]> {
  const { data } = await api.get<Benchmark[]>(`/api/v1/organizations/${orgId}/benchmarks`);
  return data;
}

/**
 * Записать справочник целиком. Справочник правится как таблица: строку удаляют,
 * стирая её, а не отдельным запросом, — частичные обновления развели бы экран и
 * хранилище (что видно на экране, то и сохранено).
 */
export async function putBenchmarks(orgId: string, rows: BenchmarkIn[]): Promise<Benchmark[]> {
  const { data } = await api.put<Benchmark[]>(
    `/api/v1/organizations/${orgId}/benchmarks`, rows);
  return data;
}

/** Отбор записей журнала: пустые поля не отправляются — сервер получает только заданное. */
export interface AuditLogFilter {
  actor?: string;
  action?: string;
  entity_type?: string;
  since?: string;
  until?: string;
  q?: string;
}

const filled = (f: AuditLogFilter): Record<string, string> =>
  Object.fromEntries(Object.entries(f).filter(([, v]) => v));

/**
 * Журнал действий организации (152-ФЗ). Только чтение: у журнала нет операций правки
 * и удаления — журнал, который можно поправить, не журнал.
 *
 * `total` приходит **под тем же отбором**, что и записи, поэтому «показано N из M» не
 * врёт при включённом фильтре.
 */
export async function getAuditLog(orgId: string, filter: AuditLogFilter = {},
                                  limit = 200): Promise<AuditLogPage> {
  const { data } = await api.get<AuditLogPage>(
    `/api/v1/organizations/${orgId}/audit-log`, { params: { limit, ...filled(filter) } });
  return data;
}

/**
 * Выгрузка журнала в CSV под текущим отбором. Скачивается браузером как файл; сама
 * выгрузка пишется в журнал — вынос следов наружу тоже событие.
 */
export async function downloadAuditLogCsv(orgId: string, filter: AuditLogFilter = {}) {
  const { data } = await api.get<Blob>(`/api/v1/organizations/${orgId}/audit-log.csv`,
                                       { params: filled(filter), responseType: "blob" });
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = "журнал-действий.csv";
  a.click();
  URL.revokeObjectURL(url);
}
