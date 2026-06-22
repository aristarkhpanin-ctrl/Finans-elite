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
  foreign?: boolean;
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

export type AssetCategory = "equipment" | "buildings" | "land";

export interface Asset {
  name: string;
  cost: string;
  purchase_month: number;
  life_months: number;
  category?: AssetCategory;
  sale_month?: number | null;
  sale_price?: string;
}

export interface InvestmentPlan {
  assets: Asset[];
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
  profit_tax_rate: string;
  profit_tax_benefit_share: string;
  payroll_contribution_rate: string;
  property_tax_rate: string;
  vat_rate: string;
  vat_basis: VatBasis;
  inventory_method: InventoryMethod;
  production_cycle_months?: number;
  inflation_sales: string;
  inflation_direct: string;
  inflation_wages: string;
  inflation_general: string;
  min_cash_balance: string;
}

export interface StartingBalance {
  cash: string;
  fixed_assets_net: string;
  foreign_monetary: string;
  debt: string;
  paid_in_capital: string;
  retained_earnings: string;
}

export interface Company {
  starting_balance: StartingBalance;
  [key: string]: unknown;
}

export interface Environment {
  fx_open: string;
  fx_rate: string[];
  [key: string]: unknown;
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
