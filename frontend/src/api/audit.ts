// Финанс-Аудит (продукт №2): API субъектов анализа + типы модели + каталог строк ввода.
import { api } from "./client";

/** Отчётный период: подпись + тип (задаёт длину периода и приведение потоков к году). */
export interface AuditPeriod {
  label: string;
  kind: "year" | "quarter" | "month";
}

/** Пользовательский показатель: имя + формула над строками аналитической формы. */
export interface UserMetric {
  name: string;
  formula: string;
}

/** Свой норматив показателя (v2): переопределяет универсальный порог. */
export interface RatioThreshold {
  ratio: string;
  direction: "higher" | "lower";
  risk_edge: string;
  good_edge: string;
}

/** Основа отчётности: платформа её фиксирует, но не трансформирует одну в другую. */
export type ReportingStandard = "rsbu" | "ifrs" | "management";

export const REPORTING_STANDARDS: [ReportingStandard, string][] = [
  ["rsbu", "РСБУ"],
  ["ifrs", "МСФО"],
  ["management", "Управленческая"],
];

/** Поправка к статье баланса: корреспонденция — всегда капитал. */
export interface Revaluation {
  code: string;
  label: string;
  amounts: string[];
}

/** Модель субъекта: реквизиты, периоды, фактическая отчётность (код строки → ряд по периодам). */
export interface AuditModel {
  name?: string;
  currency?: string;
  industry?: string;
  reporting_standard?: ReportingStandard;
  periods: AuditPeriod[];
  balance: Record<string, string[]>;   // значения-строки (Decimal, точность без float)
  income: Record<string, string[]>;
  user_metrics?: UserMetric[];
  thresholds?: RatioThreshold[];
  revaluations?: Revaluation[];
}

export interface AuditSubjectSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  n_periods: number;
  balanced: boolean;
  industry: string;
  /** Светофор диагностики: ok | warning | risk. `null` — отчётности нет, не считалось. */
  light: string | null;
}

export interface AuditSubjectOut extends AuditSubjectSummary {
  model: AuditModel;
  balance_gap: string[];   // актив − пассив по периодам (0 — сходится)
}

// Каталог строк ввода (зеркало audit_core/lines.py).
export const ASSET_LINES: [string, string][] = [
  ["A_FIXED", "Внеоборотные активы"],
  ["A_INVENTORY", "Запасы"],
  ["A_RECEIVABLE", "Дебиторская задолженность"],
  ["A_CASH", "Денежные средства и эквиваленты"],
];
export const EQLIAB_LINES: [string, string][] = [
  ["P_EQUITY", "Капитал и резервы"],
  ["P_LONG", "Долгосрочные обязательства"],
  ["P_SHORT", "Краткосрочные обязательства"],
];
/** Справочные строки: НЕ входят в итоги баланса, нужны диагностике (модели Альтмана). */
export const MEMO_LINES: [string, string][] = [
  ["M_RETAINED", "в т.ч. нераспределённая прибыль (для диагностики)"],
  ["M_MARKET_CAP", "рыночная капитализация (только для публичных компаний)"],
];
export const INCOME_LINES: [string, string][] = [
  ["I_REVENUE", "Выручка"],
  ["I_COGS", "Себестоимость продаж"],
  ["I_OPEX", "Коммерческие и управленческие расходы"],
  ["I_INTEREST", "Проценты к уплате"],
  ["I_OTHER", "Прочие доходы/расходы (сальдо)"],
  ["I_TAX", "Налог на прибыль"],
];

/**
 * Статьи, доступные для переоценки: баланс без капитала — он корреспондирует любой
 * поправке, поэтому переоценивать его напрямую не к чему приравнять (зеркало
 * `REVALUABLE_CODES` в `audit_core/revaluation.py`).
 */
export const REVALUABLE_LINES: [string, string][] =
  [...ASSET_LINES, ...EQLIAB_LINES].filter(([code]) => code !== "P_EQUITY");

export function emptyAuditModel(): AuditModel {
  return { name: "", currency: "RUB", industry: "", periods: [{ label: "", kind: "year" }],
           balance: {}, income: {} };
}

export async function listAuditSubjects(): Promise<AuditSubjectSummary[]> {
  const { data } = await api.get<AuditSubjectSummary[]>("/api/v1/audit/subjects");
  return data;
}

export async function getAuditSubject(id: string): Promise<AuditSubjectOut> {
  const { data } = await api.get<AuditSubjectOut>(`/api/v1/audit/subjects/${id}`);
  return data;
}

export async function createAuditSubject(name: string, model: AuditModel): Promise<AuditSubjectOut> {
  const { data } = await api.post<AuditSubjectOut>("/api/v1/audit/subjects", { name, model });
  return data;
}

export async function updateAuditSubject(id: string, name: string, model: AuditModel): Promise<AuditSubjectOut> {
  const { data } = await api.put<AuditSubjectOut>(`/api/v1/audit/subjects/${id}`, { name, model });
  return data;
}

export async function deleteAuditSubject(id: string): Promise<void> {
  await api.delete(`/api/v1/audit/subjects/${id}`);
}

export async function duplicateAuditSubject(id: string): Promise<AuditSubjectOut> {
  const { data } = await api.post<AuditSubjectOut>(`/api/v1/audit/subjects/${id}/duplicate`);
  return data;
}

// --- Анализ (фаза C): аналитическая форма, тренды, коэффициенты ---

export interface AuditLineOut {
  code: string;
  label: string;
  values: string[];
  subtotal: boolean;
}
export interface AuditTrendOut {
  code: string;
  label: string;
  delta: (string | null)[];
  rate: (string | null)[];
}
export interface AuditShareOut {
  code: string;
  label: string;
  share: (string | null)[];
}
export interface AuditScoreOut {
  id: string;
  name: string;
  values: (string | null)[];
  zones: (string | null)[];      // safe | grey | distress
  note: string;
}
export interface AuditAssessmentOut {
  group: string;
  name: string;
  status: (string | null)[];     // good | warn | risk
}
export interface AuditDiagnostics {
  light: string;                 // ok | warning | risk
  summary: string;
  scores: AuditScoreOut[];
  assessments: AuditAssessmentOut[];
}

export interface AuditUserMetricOut {
  name: string;
  values: string[];
  error: string | null;
}

export interface AuditAnalysis {
  n: number;
  periods: string[];
  balance: AuditLineOut[];
  income: AuditLineOut[];
  horizontal: AuditTrendOut[];
  vertical: AuditShareOut[];
  ratios: Record<string, Record<string, (string | null)[]>>;
  balance_gap: string[];
  balanced: boolean;
  diagnostics: AuditDiagnostics | null;
  user_metrics: AuditUserMetricOut[];
  revalued: boolean;          // числа посчитаны после переоценки статей
  opinion: string;
  warnings: string[];
  input_issues: AuditInputIssue[];
}

/** Находка о качестве ввода: что не так с самими данными (не с финансовым состоянием). */
export interface AuditInputIssue {
  code: string;
  /** `error` — данные противоречивы; `warning` — часть показателей не выйдет; `info`. */
  severity: "error" | "warning" | "info";
  title: string;
  detail: string;
  periods: number[];          // индексы затронутых периодов (пусто — вся модель)
  evidence: Record<string, string>;
}

/** Человекочитаемые названия групп коэффициентов (порядок вывода). */
export const RATIO_GROUPS: [string, string][] = [
  ["liquidity", "Ликвидность"],
  ["gearing", "Финансовая устойчивость"],
  ["profitability", "Рентабельность"],
  ["activity", "Деловая активность"],
];

export async function analyzeAuditSubject(id: string): Promise<AuditAnalysis> {
  const { data } = await api.post<AuditAnalysis>(`/api/v1/audit/subjects/${id}/analyze`);
  return data;
}

/** Скачать документ заключения (DOCX) авторизованным запросом. */
export async function downloadAuditReport(id: string, filename: string): Promise<void> {
  const { data } = await api.get(`/api/v1/audit/subjects/${id}/report.docx`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// --- Консолидация группы (фаза H) ---

export interface AuditConsolidation {
  analysis: AuditAnalysis;
  members: string[];
  periods_used: string[];
  warnings: string[];
  /** Участники сохранённой группы, которых больше нет (субъект удалён). */
  missing_members: string[];
}

/**
 * Внутригрупповые величины к исключению из свода (по периодам). Каждая вычитается парно
 * по обе стороны баланса, поэтому равенство «актив = пассив» сохраняется.
 */
export interface AuditElimination {
  receivables: string[];        // взаимная задолженность: дебиторка ↔ кредиторка
  revenue: string[];            // взаимная выручка: выручка ↔ себестоимость
  investments: string[];        // вложения в капитал: внеоборотные активы ↔ капитал
  unrealized_profit: string[];  // нереализованная прибыль в запасах: запасы ↔ капитал
}

/** Свести отчётность выбранных субъектов и проанализировать группу как одно предприятие. */
export async function consolidateAudit(
  subjectIds: string[],
  name: string,
  elimination?: AuditElimination,
): Promise<AuditConsolidation> {
  const { data } = await api.post<AuditConsolidation>("/api/v1/audit/consolidate", {
    subject_ids: subjectIds,
    name,
    elimination: elimination ?? null,
  });
  return data;
}

// --- Сохранённые группы предприятий (v2) ---

/** Участник группы: ссылка на субъект + имя на момент сохранения (для выбывших). */
export interface AuditGroupMember {
  subject_id: string;
  name: string;
}

/** Состав группы: участники + внутригрупповые обороты (результат не хранится). */
export interface AuditGroupModel {
  members: AuditGroupMember[];
  elimination: AuditElimination | null;
}

export interface AuditGroupSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  n_members: number;
  n_missing: number;    // сколько участников больше не существует
}

export interface AuditGroupOut extends AuditGroupSummary {
  model: AuditGroupModel;
}

export async function listAuditGroups(): Promise<AuditGroupSummary[]> {
  const { data } = await api.get<AuditGroupSummary[]>("/api/v1/audit/groups");
  return data;
}

export async function getAuditGroup(id: string): Promise<AuditGroupOut> {
  const { data } = await api.get<AuditGroupOut>(`/api/v1/audit/groups/${id}`);
  return data;
}

export async function createAuditGroup(name: string, model: AuditGroupModel): Promise<AuditGroupOut> {
  const { data } = await api.post<AuditGroupOut>("/api/v1/audit/groups", { name, model });
  return data;
}

export async function updateAuditGroup(id: string, name: string,
                                       model: AuditGroupModel): Promise<AuditGroupOut> {
  const { data } = await api.put<AuditGroupOut>(`/api/v1/audit/groups/${id}`, { name, model });
  return data;
}

export async function deleteAuditGroup(id: string): Promise<void> {
  await api.delete(`/api/v1/audit/groups/${id}`);
}

/** Свод сохранённой группы по текущей отчётности участников. */
export async function analyzeAuditGroup(id: string): Promise<AuditConsolidation> {
  const { data } = await api.post<AuditConsolidation>(`/api/v1/audit/groups/${id}/analyze`);
  return data;
}
