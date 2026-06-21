import { api } from "./client";
import type { ProjectDetail, ProjectModel } from "./model";
import type { ProjectSummary } from "./types";

export async function listProjects(): Promise<ProjectSummary[]> {
  const { data } = await api.get<ProjectSummary[]>("/api/v1/projects");
  return data;
}

export async function getProject(id: string): Promise<ProjectDetail> {
  const { data } = await api.get<ProjectDetail>(`/api/v1/projects/${id}`);
  return data;
}

export async function createProject(name: string, durationMonths = 12): Promise<ProjectDetail> {
  // Минимальная модель — backend заполнит остальные разделы значениями по умолчанию.
  const model = { header: { name, duration_months: durationMonths } };
  const { data } = await api.post<ProjectDetail>("/api/v1/projects", { name, model });
  return data;
}

export async function updateProject(id: string, name: string, model: ProjectModel): Promise<ProjectDetail> {
  const { data } = await api.put<ProjectDetail>(`/api/v1/projects/${id}`, { name, model });
  return data;
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/api/v1/projects/${id}`);
}
