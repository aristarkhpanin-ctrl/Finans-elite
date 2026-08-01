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

/** Модель субъекта: реквизиты, периоды, фактическая отчётность (код строки → ряд по периодам). */
export interface AuditModel {
  name?: string;
  currency?: string;
  industry?: string;
  periods: AuditPeriod[];
  balance: Record<string, string[]>;   // значения-строки (Decimal, точность без float)
  income: Record<string, string[]>;
  user_metrics?: UserMetric[];
  thresholds?: RatioThreshold[];
}

export interface AuditSubjectSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  n_periods: number;
  balanced: boolean;
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
];
export const INCOME_LINES: [string, string][] = [
  ["I_REVENUE", "Выручка"],
  ["I_COGS", "Себестоимость продаж"],
  ["I_OPEX", "Коммерческие и управленческие расходы"],
  ["I_INTEREST", "Проценты к уплате"],
  ["I_OTHER", "Прочие доходы/расходы (сальдо)"],
  ["I_TAX", "Налог на прибыль"],
];

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
  opinion: string;
  warnings: string[];
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
}

/** Внутригрупповые обороты к исключению из свода (по периодам). */
export interface AuditElimination {
  receivables: string[];
  revenue: string[];
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
