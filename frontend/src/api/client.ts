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

/**
 * Отказ валидации (422) в человеческом виде: **какое поле** и **что с ним не так**.
 *
 * FastAPI отвечает списком ошибок с путём (`loc`) и техническим текстом pydantic. До
 * этого экран показывал общее «не удалось сохранить»: правка всей модели отклонялась
 * из-за одной ячейки, а какой — не знал никто, и введённое приходилось искать глазами.
 *
 * Путь печатается как есть (`obligations → 1 → amount`): переводить ключи модели
 * значило бы завести словарь, который молча отстанет от неё. Зато сказано, **что**
 * не так — и для числа названо, как его писать.
 */
export function httpFieldError(e: unknown): string | undefined {
  if (!axios.isAxiosError(e)) return undefined;
  const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail;
  if (!Array.isArray(detail) || detail.length === 0) return undefined;
  const first = detail[0] as { loc?: unknown[]; type?: string; input?: unknown };
  // `body` и `model` — обёртка запроса, а не то, что заполнял человек.
  const path = (first.loc ?? [])
    .filter((p) => p !== "body" && p !== "model")
    .map((p) => (typeof p === "number" ? p + 1 : String(p)))
    .join(" → ");
  const kind = String(first.type ?? "");
  const numeric = kind.includes("decimal") || kind.includes("float") || kind.includes("int");
  const subject = typeof first.input === "string" && first.input.trim() !== ""
    ? `«${first.input}»` : "значение";
  const where = path ? ` в поле «${path}»` : "";
  return numeric
    ? `${subject}${where} не читается как число. Десятичный разделитель — запятая или `
      + "точка, разряды можно разделить пробелом: 1 200,50"
    : `${subject}${where} не подходит по формату`;
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
