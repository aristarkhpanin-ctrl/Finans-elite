import { api } from "./client";
import type { Schema } from "./gen";

export const SENSITIVITY_PARAMS: [string, string][] = [
  ["sales_price", "Цена сбыта"],
  ["sales_volume", "Объём сбыта"],
  ["direct_costs", "Прямые издержки"],
  ["fixed_costs", "Постоянные издержки"],
  ["discount_rate", "Ставка дисконтирования"],
];

// Ответы — из сгенерированной OpenAPI-схемы; входные тела запросов — руками
// (у kind — строгий union, точнее бэкендового str).

// --- Чувствительность ---
export type SensitivityPoint = Schema<"SensitivityPointOut">;
export type SensitivityResponse = Schema<"SensitivityResponse">;
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
export type HistogramBin = Schema<"HistogramBinOut">;
export type MonteCarloResponse = Schema<"MonteCarloResponse">;
export type JobSubmit = Schema<"JobSubmitResponse">;
export type JobStatus = Schema<"JobStatusResponse">;

type MonteCarloBody = { iterations: number; seed: number; uncertain: UncertainParamIn[] };

export async function runMonteCarlo(id: string, body: MonteCarloBody): Promise<MonteCarloResponse> {
  const { data } = await api.post<MonteCarloResponse>(`/api/v1/projects/${id}/monte-carlo`, body);
  return data;
}

/** Поставить Монте-Карло в очередь (фоновый воркер) → id задачи. */
export async function submitMonteCarloAsync(id: string, body: MonteCarloBody): Promise<JobSubmit> {
  const { data } = await api.post<JobSubmit>(`/api/v1/projects/${id}/monte-carlo/async`, body);
  return data;
}

/** Опросить статус/результат фоновой задачи анализа. */
export async function getJob(jobId: string): Promise<JobStatus> {
  const { data } = await api.get<JobStatus>(`/api/v1/analysis/jobs/${jobId}`);
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
export type ScenarioResult = Schema<"ScenarioResultOut">;
export type WhatIfResponse = Schema<"WhatIfResponse">;
export async function runWhatIf(
  id: string,
  scenarios: ScenarioIn[],
  includeBase = true,
): Promise<WhatIfResponse> {
  const { data } = await api.post<WhatIfResponse>(`/api/v1/projects/${id}/what-if`, {
    scenarios,
    include_base: includeBase,
  });
  return data;
}
