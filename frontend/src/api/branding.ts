import { useQuery } from "@tanstack/react-query";
import { api, getOrgId } from "./client";
import type { Schema } from "./gen";

// Логотип организации в документах (пакет L, L9) — типы из OpenAPI-схемы.
export type OrgLogo = Schema<"OrgLogoOut">;

/** Предел файла — для проверки до отправки. Точный отказ и его причина — с сервера. */
export const MAX_LOGO_BYTES = 256 * 1024;

export async function getOrgLogo(orgId: string): Promise<OrgLogo> {
  const { data } = await api.get<OrgLogo>(`/api/v1/organizations/${orgId}/logo`);
  return data;
}

export async function setOrgLogo(orgId: string, dataBase64: string): Promise<OrgLogo> {
  const { data } = await api.put<OrgLogo>(`/api/v1/organizations/${orgId}/logo`,
                                          { data_base64: dataBase64 });
  return data;
}

export async function deleteOrgLogo(orgId: string): Promise<void> {
  await api.delete(`/api/v1/organizations/${orgId}/logo`);
}

/** Содержимое файла в base64 — без префикса `data:…;base64,`: тип сервер определяет по
 *  самому файлу, а не по тому, что заявил браузер. */
export function fileToBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result ?? "");
      resolve(url.slice(url.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error ?? new Error("Файл не прочитан"));
    reader.readAsDataURL(file);
  });
}

/**
 * Логотип для печатного бланка. Нет организации или логотипа — `null`, и бланк выходит
 * с маркой платформы; ошибка запроса бланк не роняет — печатается без логотипа.
 */
export function useOrgLogo(orgId: string | null | undefined): OrgLogo | null {
  const { data } = useQuery({
    queryKey: ["org-logo", orgId],
    queryFn: () => getOrgLogo(orgId as string),
    enabled: !!orgId,
    staleTime: 60_000,
  });
  return data?.present ? data : null;
}

/**
 * Логотип текущей организации для печатного бланка (`PrintReport`, `AuditPrintReport`).
 * Организация — та же, от имени которой идут запросы (`getOrgId`): бланк печатает её
 * документ. Нет логотипа — `null`, и бланк выходит с маркой платформы.
 */
export function usePrintBrand(): { src: string; name: string } | null {
  const logo = useOrgLogo(getOrgId());
  if (!logo?.data_url) return null;
  return { src: logo.data_url, name: logo.organization || "организация" };
}
