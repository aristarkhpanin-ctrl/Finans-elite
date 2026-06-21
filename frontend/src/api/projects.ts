import { api } from "./client";
import type { ProjectSummary } from "./types";

export async function listProjects(): Promise<ProjectSummary[]> {
  const { data } = await api.get<ProjectSummary[]>("/api/v1/projects");
  return data;
}
