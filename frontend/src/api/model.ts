// Типы модели проекта (зеркало backend ProjectModel).
// Decimal сериализуется как строка; целые (месяцы/сроки) — number.

export interface PaymentTerms {
  prepayment_share: string;
  advance_lead_months: number;
  payment_delay_months: number;
}

export interface Product {
  id: string;
  name: string;
}

export interface SalesLine {
  product_id: string;
  volume: string[];
  price: string[];
  payment: PaymentTerms;
}

export interface ProductionLine {
  product_id: string;
  volume: string[];
}

export type DirectCostKind = "materials" | "piece_wages";

export interface DirectCostLine {
  name: string;
  kind: DirectCostKind;
  amount: string[];
  payment_delay_months: number;
  stock_lead_months: number;
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
}

export interface OperatingPlan {
  products: Product[];
  sales: SalesLine[];
  production: ProductionLine[];
  direct_costs: DirectCostLine[];
  fixed_costs: FixedCostLine[];
}

export type RepaymentType = "equal_principal" | "bullet";

export interface Loan {
  name: string;
  amount: string;
  start_month: number;
  term_months: number;
  annual_rate: string;
  repayment: RepaymentType;
}

export interface EquityInjection {
  amount: string;
  month: number;
}

export interface AutoFinancing {
  enabled: boolean;
  annual_rate: string;
  min_balance: string;
}

export interface Financing {
  loans: Loan[];
  equity: EquityInjection[];
  dividends: string[];
  common_shares: string;
  auto_financing: AutoFinancing;
}

export interface Asset {
  name: string;
  cost: string;
  purchase_month: number;
  life_months: number;
}

export interface InvestmentPlan {
  assets: Asset[];
}

export interface ProjectHeader {
  name: string;
  start_date: string;
  duration_months: number;
}

export interface ProjectSettings {
  discount_rate_annual: string;
  profit_tax_rate: string;
  property_tax_rate: string;
  vat_rate: string;
  min_cash_balance: string;
}

export interface ProjectModel {
  header: ProjectHeader;
  settings: ProjectSettings;
  operating_plan: OperatingPlan;
  investment_plan: InvestmentPlan;
  financing: Financing;
  // Прочие разделы (company, environment, actualization) проходят насквозь.
  [key: string]: unknown;
}

export interface ProjectDetail {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  model: ProjectModel;
}

export const COST_FUNCTION_LABELS: Record<CostFunction, string> = {
  admin: "Административные",
  production: "Производственные",
  marketing: "Маркетинговые",
  staff_admin: "Зарплата (адм.)",
  staff_production: "Зарплата (произв.)",
  staff_marketing: "Зарплата (маркет.)",
};
