import { api } from "./client";
import type { Schema } from "./gen";
import type { ProjectDetail } from "./model";

// Версии проекта и анализ изменений (пакет №8, gap 4.4) — из OpenAPI-схемы.
export type VersionSummary = Schema<"VersionSummary">;
export type VersionOut = Schema<"VersionOut">;
export type VersionDiff = Schema<"VersionDiffOut">;
export type ModelChange = Schema<"ModelChangeOut">;
export type MetricChange = Schema<"MetricChangeOut">;

export async function listVersions(projectId: string): Promise<VersionSummary[]> {
  const { data } = await api.get<VersionSummary[]>(`/api/v1/projects/${projectId}/versions`);
  return data;
}

export async function createVersion(projectId: string, label: string): Promise<VersionSummary> {
  const { data } = await api.post<VersionSummary>(`/api/v1/projects/${projectId}/versions`, { label });
  return data;
}

/** Диф версии с другой версией или текущей рабочей моделью (against = id | "current"). */
export async function diffVersion(projectId: string, versionId: string,
                                  against = "current"): Promise<VersionDiff> {
  const { data } = await api.get<VersionDiff>(
    `/api/v1/projects/${projectId}/versions/${versionId}/diff`, { params: { against } });
  return data;
}

export async function restoreVersion(projectId: string, versionId: string): Promise<ProjectDetail> {
  const { data } = await api.post<ProjectDetail>(
    `/api/v1/projects/${projectId}/versions/${versionId}/restore`);
  return data;
}

export async function deleteVersion(projectId: string, versionId: string): Promise<void> {
  await api.delete(`/api/v1/projects/${projectId}/versions/${versionId}`);
}
