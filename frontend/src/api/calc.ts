import { api } from "./client";
import type { Schema } from "./gen";

// Типы отчётов/показателей — из сгенерированной OpenAPI-схемы (см. gen.ts).
export type LineOut = Schema<"LineOut">;
export type StatementOut = Schema<"StatementOut">;
export type MetricsOut = Schema<"MetricsOut">;
export type RatioGroup = Record<string, (string | null)[]>;
export type RatiosOut = Schema<"RatiosOut">;
export type BreakEvenOut = Schema<"BreakEvenOut">;
export type ValuationOut = Schema<"ValuationOut">;
export type CalcResponse = Schema<"CalcResponse">;

export async function calculateProject(id: string): Promise<CalcResponse> {
  const { data } = await api.post<CalcResponse>(`/api/v1/projects/${id}/calculate`);
  return data;
}

export function line(stmt: StatementOut, code: string): string[] {
  return stmt.lines.find((l) => l.code === code)?.values ?? [];
}
