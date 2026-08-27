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
  earnings_adjustments?: EarningsAdjustment[];
  obligations?: Obligation[];
  procedure_marks?: ProcedureMark[];
  custom_procedures?: CustomProcedure[];
}

/** Статус процедуры, который ставит человек (системный выводится из прогона). */
export type MarkStatus = "pending" | "done" | "skipped";

export const MARK_STATUSES: [MarkStatus, string][] = [
  ["pending", "Не отмечено"],
  ["done", "Выполнено"],
  ["skipped", "Снято"],
];

/**
 * Отметка аналитика по процедуре каталога (SPEC, Прил. М.3). Ставится только у
 * процедур с исполнителем «аналитик»; причина при снятии обязательна — процедура,
 * снятая молча, неотличима от забытой.
 */
export interface ProcedureMark {
  code: string;
  status: MarkStatus;
  note: string;
}

/** Своя процедура аналитика (SPEC, Прил. М.5): платформа её не выполняет. */
export interface CustomProcedure {
  title: string;
  status: MarkStatus;
  note: string;
}

export function emptyCustomProcedure(): CustomProcedure {
  return { title: "", status: "pending", note: "" };
}

/** Вид обязательства → подпись; забалансовость — свойство вида, а не отдельная галочка. */
export type ObligationKind =
  "credit" | "lease" | "loan" | "other" | "guarantee" | "pledge_third_party";

export const OBLIGATION_KINDS: [ObligationKind, string, boolean][] = [
  ["credit", "Кредит банка", false],
  ["lease", "Лизинг", false],
  ["loan", "Займ (в т.ч. участника)", false],
  ["other", "Иное балансовое обязательство", false],
  ["guarantee", "Поручительство за третье лицо", true],
  ["pledge_third_party", "Залог за третье лицо", true],
];

export const isOffBalanceKind = (kind: ObligationKind): boolean =>
  OBLIGATION_KINDS.find(([k]) => k === kind)?.[2] ?? false;

/** Статус ковенанта: ставится человеком, `unknown` — по умолчанию и не значит «в норме». */
export type CovenantStatus = "ok" | "breached" | "unknown";

export const COVENANT_STATUSES: [CovenantStatus, string][] = [
  ["unknown", "Не проверен"],
  ["ok", "Соблюдён"],
  ["breached", "Нарушен"],
];

/**
 * Обязательство реестра (SPEC, Приложение Л). `rate`/`maturity_year` — `null`, когда
 * не указаны: беспроцентный займ (0%) и займ без ставки — разные факты, как и
 * «погашение в 2029» против «срок не заполнен».
 */
export interface Obligation {
  creditor: string;
  contract: string;
  kind: ObligationKind;
  amount: string;
  rate: string | null;
  maturity_year: number | null;
  on_demand: boolean;
  collateral: string;
  pledged_amount: string;
  covenant: string;
  covenant_status: CovenantStatus;
  covenant_note: string;
}

export function emptyObligation(): Obligation {
  return { creditor: "", contract: "", kind: "credit", amount: "", rate: null,
           maturity_year: null, on_demand: false, collateral: "", pledged_amount: "",
           covenant: "", covenant_status: "unknown", covenant_note: "" };
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
/** Справочная строка ОФР: без неё EBITDA не существует (SPEC, Приложение К.1). */
export const INCOME_MEMO_LINES: [string, string][] = [
  ["M_DEPRECIATION", "в т.ч. амортизация (для EBITDA)"],
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

/** Завести демо-дело из эталонного семпла — обычное дело с вымышленными данными. */
export async function createDemoAuditSubject(): Promise<AuditSubjectOut> {
  const { data } = await api.post<AuditSubjectOut>("/api/v1/audit/subjects/demo");
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
  flags: AuditFlagRegistry;
  earnings: AuditEarnings;
  obligations: AuditObligations;
  procedures: AuditProcedures;
}

/** Итог процедуры: `pass|finding|no_data` выводится из прогона, остальное — отметка. */
export type ProcedureStatus =
  "pass" | "finding" | "no_data" | "done" | "skipped" | "pending";

export interface AuditProcedure {
  code: string;
  group: string;
  title: string;
  source: "system" | "analyst";
  method: string;
  status: ProcedureStatus;
  detail: string;
  findings: string[];
}

/**
 * Чек-лист процедур (SPEC, Прил. М). `coverage` честен только вместе с `limits`:
 * «охват 70%» без перечня тех 30% читается как «почти всё проверено».
 */
export interface AuditProcedures {
  items: AuditProcedure[];
  total: number;
  closed: number;
  passed: number;
  findings: number;
  no_data: number;
  done: number;
  skipped: number;
  pending: number;
  coverage: string | null;
  limits: string[];
}

/** Строка реестра: введённое + то, что следует из вида обязательства. */
export interface AuditObligationRow {
  creditor: string;
  contract: string;
  kind: string;
  kind_label: string;
  off_balance: boolean;
  amount: string;
  rate: string | null;
  maturity: string;              // «2029» | «по требованию» | «срок не указан»
  on_demand: boolean;
  collateral: string;
  pledged_amount: string;
  covenant: string;
  covenant_status: CovenantStatus;
  covenant_note: string;
}

/** Сколько долга упирается в год погашения (не платёж года — график не вводится). */
export interface AuditMaturityBucket {
  label: string;
  amount: string;
  kind: "year" | "on_demand" | "unknown";
}

/**
 * Реестр обязательств: два итога, которые **никогда не складываются** (SPEC, Прил. Л.1),
 * и сверка с балансом. `free_assets` — `null`, когда активов нет: сравнивать не с чем.
 */
export interface AuditObligations {
  rows: AuditObligationRow[];
  balance_debt: string;
  off_balance: string;
  reported_debt: string;
  discrepancy: string;
  reconciled: boolean;
  buckets: AuditMaturityBucket[];
  pledged_total: string;
  free_assets: string | null;
  pledged_share: string | null;
  covenants_breached: number;
  covenants_unknown: number;
}

/** Вид корректировки при нормализации прибыли (SPEC, Приложение К.2). */
export type AdjustmentKind =
  "one_off" | "owner" | "related_party" | "non_operating" | "accounting";

export const ADJUSTMENT_KINDS: [AdjustmentKind, string][] = [
  ["one_off", "Разовый доход или расход"],
  ["owner", "Вознаграждение собственника сверх рыночного"],
  ["related_party", "Сделка со связанной стороной не по рынку"],
  ["non_operating", "Непрофильная деятельность"],
  ["accounting", "Учётное искажение"],
];

/** Поправка нормализации: со знаком, с обязательной причиной. */
export interface EarningsAdjustment {
  label: string;
  kind: AdjustmentKind;
  amounts: string[];
}

export interface AuditAppliedAdjustment {
  label: string;
  kind: string;
  kind_label: string;
  amounts: string[];
  total: string;
}

/**
 * Нормализация показателя прибыли. `base_code` — что именно нормализовано: EBITDA
 * (введена амортизация) или EBIT. Показывать это имя обязательно: показатели
 * различаются на всю амортизацию, и мультипликатор, применённый не к тому, ошибётся
 * ровно на неё.
 */
export interface AuditEarnings {
  base_code: string;
  reported: string[];
  normalized: string[];
  adjustments: AuditAppliedAdjustment[];
  grade: string | null;          // A | B | C; null — сравнивать не с чем
  grade_note: string;
  deviation: string | null;
}

/** Красный флаг: что настораживает, в каких периодах и на сколько рублей. */
export interface AuditFlag {
  code: string;
  severity: "risk" | "warning";
  title: string;
  detail: string;
  periods: number[];
  /** Денежная мера. `null` — её не существует, а не «ноль рублей». */
  impact: string | null;
  evidence: Record<string, string>;
}

/** Реестр флагов: сумма оценённых + число тех, у кого денежной меры нет вовсе. */
export interface AuditFlagRegistry {
  flags: AuditFlag[];
  priced_total: string;
  unpriced: number;
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
