import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { listProjects } from "../api/projects";

export function ProjectsPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  return (
    <div>
      <h1>{t("projects.title")}</h1>
      {isLoading && <p className="muted">{t("common.loading")}</p>}
      {isError && <p className="error">{t("auth.genericError")}</p>}
      {data && data.length === 0 && <p className="muted">{t("projects.empty")}</p>}
      {data && data.length > 0 && (
        <div className="list">
          {data.map((p) => (
            <div className="list-item" key={p.id}>
              <strong>{p.name}</strong>
              <span className="muted">
                {t("projects.created")} {new Date(p.created_at).toLocaleDateString("ru-RU")}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
