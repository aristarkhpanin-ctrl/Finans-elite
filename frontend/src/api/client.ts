import axios from "axios";

const TOKEN_KEY = "fe_token";
const ORG_KEY = "fe_org";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getOrgId(): string | null {
  return localStorage.getItem(ORG_KEY);
}
export function setOrgId(orgId: string | null) {
  if (orgId) localStorage.setItem(ORG_KEY, orgId);
  else localStorage.removeItem(ORG_KEY);
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
});

/** HTTP-статус из ошибки axios (или undefined — не сетевая/HTTP ошибка). */
export function httpStatus(e: unknown): number | undefined {
  return axios.isAxiosError(e) ? e.response?.status : undefined;
}

/** Текст `detail` из тела ответа об ошибке (FastAPI), если он строковый. */
export function httpDetail(e: unknown): string | undefined {
  if (axios.isAxiosError(e)) {
    const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
  }
  return undefined;
}

// Подставляем токен и текущую организацию в каждый запрос.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const org = getOrgId();
  if (org) config.headers["X-Organization-Id"] = org;
  return config;
});

// При 401 — разлогиниваем и отправляем на вход.
api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error?.response?.status === 401) {
      setToken(null);
      if (location.pathname !== "/login") location.assign("/login");
    }
    return Promise.reject(error);
  },
);
