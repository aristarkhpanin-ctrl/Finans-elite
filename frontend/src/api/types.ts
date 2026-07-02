// Типы данных API (см. backend схемы).

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
}

export interface OrganizationMembership {
  id: string;
  name: string;
  role: string;
  created_at: string;
}

/** Сводка последнего успешного расчёта (B1); Decimal — строками. */
export interface LastCalc {
  npv: string;
  irr_annual: string | null;
  pb_months: number | null;
  engine_version: string;
  calculated_at: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  last_calc: LastCalc | null;
  /** Модель менялась после последнего расчёта (или расчёта не было). */
  is_stale: boolean;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}
