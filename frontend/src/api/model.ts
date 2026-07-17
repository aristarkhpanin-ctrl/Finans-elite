// Типы модели проекта (зеркало backend ProjectModel).
// Decimal сериализуется как строка; целые (месяцы/сроки) — number.

export interface PaymentPart {
  /** < 0 — предоплата за |offset| мес. до отгрузки; > 0 — рассрочка после отгрузки. */
  offset_months: number;
  share: string;
}

export interface PaymentTerms {
  prepayment_share: string;
  advance_lead_months: number;
  payment_delay_months: number;
  /** Непустой график долей заменяет простые поля; остаток до 1 — в месяце отгрузки. */
  schedule?: PaymentPart[];
}

export interface Material {
  id: string;
  name?: string;
  unit?: string;
  unit_price?: string;
  payment_delay_months?: number;
  stock_lead_months?: number;
  foreign?: boolean;
}

export interface BomLine {
  material_id: string;
  qty_per_unit?: string;
}

export interface Product {
  id: string;
  name: string;
  /** Рецептура (BOM): нормы расхода материалов + сдельная ЗП на единицу. */
  bom?: BomLine[];
  piece_wage_per_unit?: string;
}

export interface SalesLine {
  product_id: string;
  volume: string[];
  price: string[];
  payment: PaymentTerms;
  foreign?: boolean;
  start_month?: number | null;
  /** Ставка НДС строки (напр. "0.10"); null/пусто — глобальная. */
  vat_rate?: string | null;
}

export interface ProductionLine {
  product_id: string;
  volume: string[];
  start_month?: number | null;
}

export type DirectCostKind = "materials" | "piece_wages";

export interface DirectCostLine {
  name: string;
  kind: DirectCostKind;
  amount: string[];
  payment_delay_months: number;
  stock_lead_months: number;
  foreign?: boolean;
}

export type CostFunction =
  | "admin"
  | "production"
  | "marketing"
  | "staff_admin"
  | "staff_production"
  | "staff_marketing";

export interface FixedCostLine {
  name: string;
  function: CostFunction;
  amount: string[];
  payment_delay_months: number;
  from_profit?: boolean;
  foreign?: boolean;
}

export interface OperatingPlan {
  products: Product[];
  sales: SalesLine[];
  production: ProductionLine[];
  direct_costs: DirectCostLine[];
  fixed_costs: FixedCostLine[];
  /** Справочник материалов для рецептур продуктов. */
  materials?: Material[];
  /** Прочие поступления/выплаты (вне основной деятельности) → I20/C10 и I21|I24/C11. */
  other_income?: OtherFlow[];
  other_expenses?: OtherFlow[];
  /** План персонала: штатные позиции → затраты на персонал (I13–I15) + взносы. */
  staff?: StaffPosition[];
}

export interface StaffPosition {
  name: string;
  monthly_salary: string;
  headcount?: string;
  start_month?: number;
  /** Исключительно; null/пусто — до конца горизонта. */
  end_month?: number | null;
  function?: CostFunction;
  payment_delay_months?: number;
}

export interface OtherFlow {
  name: string;
  amount: string[];
  /** Только для выплат: невычитаемая («из прибыли») — идёт в I24. */
  from_profit?: boolean;
}

export type RepaymentType = "equal_principal" | "bullet";

export interface Loan {
  name: string;
  amount: string;
  start_month: number;
  term_months: number;
  annual_rate: string;
  repayment: RepaymentType;
  interest_on_profit?: boolean;
  foreign?: boolean;
}

export interface Lease {
  name: string;
  monthly_payment: string;
  start_month: number;
  term_months: number;
  finance?: boolean;
  annual_rate?: string;
  insurance_monthly?: string;
  buyout_price?: string;
  buyout_life_months?: number;
}

export interface Deposit {
  name: string;
  amount: string;
  start_month: number;
  term_months: number;
  annual_rate: string;
}

export interface EquityInjection {
  amount: string;
  month: number;
}

export interface AutoFinancing {
  enabled: boolean;
  annual_rate: string;
  min_balance: string;
  /** Авторазмещение излишков кассы в депозит (симметрично автокредиту). */
  invest_surplus?: boolean;
  invest_annual_rate?: string;
}

export interface Financing {
  loans: Loan[];
  leases?: Lease[];
  deposits?: Deposit[];
  equity: EquityInjection[];
  dividends: string[];
  common_shares: string;
  auto_financing: AutoFinancing;
}

export type AssetCategory = "equipment" | "buildings" | "land" | "intangible";

export interface AdditionalInvestment {
  month: number;
  amount: string;
}

export interface Asset {
  name: string;
  cost: string;
  purchase_month: number;
  life_months: number;
  category?: AssetCategory;
  sale_month?: number | null;
  sale_price?: string;
  /** Переоценка: месяц и сумма дооценки (±) → остаточная B9 и добавочный капитал B31. */
  revaluation_month?: number | null;
  revaluation_amount?: string;
  /** Доинвестирование (модернизация): вложения, амортизируемые от остаточного срока. */
  additional_investments?: AdditionalInvestment[];
}

export type StageKind = "expense" | "asset" | "production";
export type CostTiming = "uniform" | "on_finish";

export interface Resource {
  id: string;
  name?: string;
  unit_price?: string;
  payment_delay_months?: number;
}

export interface StageResource {
  resource_id: string;
  quantity?: string;
}

export interface Stage {
  id: string;
  name?: string;
  kind?: StageKind;
  start_month?: number;
  duration_months?: number;
  predecessor_id?: string | null;
  parent_id?: string | null;
  cost?: string;
  resources?: StageResource[];
  cost_timing?: CostTiming;
  amortize_months?: number;
  asset_life_months?: number;
  asset_category?: AssetCategory;
  product_id?: string | null;
  /** Актуализация этапа (план-факт, gap 4.6): фактические сроки/стоимость. */
  actual_start_month?: number | null;
  actual_finish_month?: number | null;
  actual_cost?: string | null;
}

export interface CalendarPlan {
  stages: Stage[];
  resources: Resource[];
}

export interface InvestmentPlan {
  assets: Asset[];
  calendar?: CalendarPlan;
}

export interface ProjectHeader {
  name: string;
  start_date: string;
  duration_months: number;
}

export interface Actualization {
  actual_until: number;
  actuals: Record<string, string[]>;
}

export type VatBasis = "shipment" | "payment";
export type InventoryMethod = "average" | "fifo";

export interface ProjectSettings {
  discount_rate_annual: string;
  /** Ставка дисконтирования во второй валюте (0 = выключено; показатели дублируются). */
  discount_rate_annual_foreign?: string;
  terminal_growth_rate?: string;
  valuation_earnings_multiple?: string;
  liquidation_recovery_rate?: string;
  profit_tax_rate: string;
  profit_tax_benefit_share: string;
  /** Ставка рефинансирования ЦБ (0 = норматив процентов выключен) и коэффициент нормы. */
  cb_refinancing_rate?: string;
  interest_norm_multiple?: string;
  /** Периодичность уплаты налога на прибыль и НДС (месяц/квартал/год). */
  profit_tax_periodicity?: "month" | "quarter" | "year";
  vat_periodicity?: "month" | "quarter" | "year";
  payroll_contribution_rate: string;
  property_tax_rate: string;
  sales_tax_rate?: string;
  vat_rate: string;
  vat_basis: VatBasis;
  inventory_method: InventoryMethod;
  production_cycle_months?: number;
  inflation_sales: string;
  inflation_direct: string;
  inflation_wages: string;
  inflation_general: string;
  /** Погодовые ряды инфляции (по годам); непустой ряд переопределяет константу. */
  inflation_sales_series?: string[];
  inflation_direct_series?: string[];
  inflation_wages_series?: string[];
  inflation_general_series?: string[];
  min_cash_balance: string;
}

export interface StartingBalance {
  cash: string;
  fixed_assets_net: string;
  foreign_monetary: string;
  receivables?: string;
  payables?: string;
  raw_materials?: string;
  finished_goods?: string;
  prepaid_expenses?: string;
  advances_received?: string;
  short_term_debt?: string;
  debt: string;
  paid_in_capital: string;
  preferred_capital?: string;
  reserves?: string;
  additional_capital?: string;
  retained_earnings: string;
}

export interface Company {
  starting_balance: StartingBalance;
  [key: string]: unknown;
}

/** Настраиваемый налог (SPEC §22.9): база × ставка, периодичность уплаты, отнесение. */
export interface CustomTax {
  name: string;
  rate: string;
  base: "revenue" | "payroll" | "property" | "profit" | "formula";
  formula?: string;
  periodicity: "month" | "quarter" | "year";
  allocation: "expense" | "profit";
}

export interface Currency {
  code: string;
  name?: string;
}

export interface Environment {
  fx_open: string;
  fx_rate: string[];
  /** Валюты проекта; вторая (currencies[1]) — при мультивалютной модели. */
  currencies?: Currency[];
  /** Настраиваемые налоги (базы — до настраиваемых налогов; пусто — выключено). */
  taxes?: CustomTax[];
  [key: string]: unknown;
}

export interface UserRow {
  name: string;
  formula: string;
}

export interface UserTable {
  id: string;
  name?: string;
  rows: UserRow[];
}

/** Текстовый раздел бизнес-плана для DOCX-документа (к расчёту отношения не имеет). */
export interface PlanSection {
  title: string;
  text: string;
}

export interface ProjectModel {
  header: ProjectHeader;
  settings: ProjectSettings;
  company: Company;
  environment: Environment;
  operating_plan: OperatingPlan;
  investment_plan: InvestmentPlan;
  financing: Financing;
  actualization: Actualization;
  /** Таблицы пользователя (строки-формулы над результатом). */
  user_tables?: UserTable[];
  /** Текстовые разделы бизнес-плана (DOCX, пакет №5). */
  business_plan?: PlanSection[];
  [key: string]: unknown;
}

export interface ProjectDetail {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  model: ProjectModel;
  // Гейт финализации (Ф10): статус, момент и снимок ревью, признак дрейфа модели.
  status?: "draft" | "finalized";
  finalized_at?: string | null;
  finalized_review?: import("./review").ReviewResponse | null;
  finalized_drift?: boolean;
}

export const COST_FUNCTION_LABELS: Record<CostFunction, string> = {
  admin: "Административные",
  production: "Производственные",
  marketing: "Маркетинговые",
  staff_admin: "Зарплата (адм.)",
  staff_production: "Зарплата (произв.)",
  staff_marketing: "Зарплата (маркет.)",
};
