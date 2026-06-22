import { api } from "./client";

export interface LineOut {
  code: string;
  label: string;
  values: string[];
}

export interface StatementOut {
  lines: LineOut[];
}

export interface MetricsOut {
  npv: string;
  irr_annual: string | null;
  pi: string | null;
  pb_months: number | null;
  dpb_months: number | null;
  pv_investments: string | null;
  peak_financing_need: string | null;
}

export type RatioGroup = Record<string, (string | null)[]>;

export interface RatiosOut {
  liquidity: RatioGroup;
  activity: RatioGroup;
  gearing: RatioGroup;
  profitability: RatioGroup;
  investment: RatioGroup;
}

export interface BreakEvenOut {
  break_even_revenue: (string | null)[];
  margin_of_safety: (string | null)[];
}

export interface ValuationOut {
  net_assets: string;
  gordon_value: string | null;
}

export interface CalcResponse {
  engine_version: string;
  n: number;
  income: StatementOut;
  cashflow: StatementOut;
  balance: StatementOut;
  profit_use: StatementOut;
  metrics: MetricsOut;
  ratios: RatiosOut;
  break_even: BreakEvenOut;
  valuation: ValuationOut;
  actualized_cashflow: StatementOut | null;
  cashflow_variance: StatementOut | null;
  warnings: string[];
}

export async function calculateProject(id: string): Promise<CalcResponse> {
  const { data } = await api.post<CalcResponse>(`/api/v1/projects/${id}/calculate`);
  return data;
}

export function line(stmt: StatementOut, code: string): string[] {
  return stmt.lines.find((l) => l.code === code)?.values ?? [];
}
