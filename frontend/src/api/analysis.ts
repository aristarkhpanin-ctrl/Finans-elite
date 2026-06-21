import { api } from "./client";

export const SENSITIVITY_PARAMS: [string, string][] = [
  ["sales_price", "Цена сбыта"],
  ["sales_volume", "Объём сбыта"],
  ["direct_costs", "Прямые издержки"],
  ["fixed_costs", "Постоянные издержки"],
  ["discount_rate", "Ставка дисконтирования"],
];

// --- Чувствительность ---
export interface SensitivityPoint {
  factor: string;
  npv: string;
  irr_annual: string | null;
}
export interface SensitivityResponse {
  param: string;
  points: SensitivityPoint[];
}
export async function runSensitivity(id: string, param: string, factors: string[]): Promise<SensitivityResponse> {
  const { data } = await api.post<SensitivityResponse>(`/api/v1/projects/${id}/sensitivity`, { param, factors });
  return data;
}

// --- Монте-Карло ---
export interface DistributionIn {
  kind: "uniform" | "normal" | "triangular";
  low?: string;
  high?: string;
  mean?: string;
  std?: string;
  mode?: string;
}
export interface UncertainParamIn {
  param: string;
  distribution: DistributionIn;
}
export interface MonteCarloResponse {
  iterations: number;
  npv_mean: string;
  npv_std: string;
  npv_min: string;
  npv_max: string;
  npv_p10: string;
  npv_p50: string;
  npv_p90: string;
  probability_npv_positive: string;
}
export async function runMonteCarlo(
  id: string,
  body: { iterations: number; seed: number; uncertain: UncertainParamIn[] },
): Promise<MonteCarloResponse> {
  const { data } = await api.post<MonteCarloResponse>(`/api/v1/projects/${id}/monte-carlo`, body);
  return data;
}

// --- What-If ---
export interface ScenarioAdjustmentIn {
  param: string;
  factor: string;
}
export interface ScenarioIn {
  name: string;
  adjustments: ScenarioAdjustmentIn[];
}
export interface ScenarioResult {
  name: string;
  npv: string;
  irr_annual: string | null;
  pi: string | null;
  pb_months: number | null;
}
export interface WhatIfResponse {
  scenarios: ScenarioResult[];
}
export async function runWhatIf(id: string, scenarios: ScenarioIn[]): Promise<WhatIfResponse> {
  const { data } = await api.post<WhatIfResponse>(`/api/v1/projects/${id}/what-if`, { scenarios });
  return data;
}
