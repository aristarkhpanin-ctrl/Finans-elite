// Типы данных API. Ответы бэкенда — псевдонимы сгенерированных из OpenAPI схем
// (см. gen.ts); имена сохранены, чтобы не трогать потребителей.
import type { Schema } from "./gen";

export type TokenResponse = Schema<"TokenResponse">;
export type User = Schema<"UserOut">;
export type OrganizationMembership = Schema<"OrganizationMembershipOut">;

/** Сводка последнего успешного расчёта (B1); Decimal — строками. */
export type LastCalc = Schema<"LastCalcOut">;
export type ProjectSummary = Schema<"ProjectSummary">;

export type RegisterPayload = Schema<"RegisterRequest">;
export type LoginPayload = Schema<"LoginRequest">;
