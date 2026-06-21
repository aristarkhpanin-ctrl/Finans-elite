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

export interface ProjectSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
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
