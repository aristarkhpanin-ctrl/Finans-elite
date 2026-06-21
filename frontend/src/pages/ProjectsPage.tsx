import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { createProject, deleteProject, listProjects } from "../api/projects";
import { Button, Card } from "../components/ui";

export function ProjectsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");

  const { data, isLoading, isError } = useQuery({ queryKey: ["projects"], queryFn: listProjects });

  const create = useMutation({
    mutationFn: () => createProject(name.trim() || "Новый проект"),
    onSuccess: (p) => {
      setName("");
      qc.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/projects/${p.id}`);
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });

  return (
    <div>
      <h1>{t("projects.title")}</h1>

      <Card style={{ marginBottom: 18 }}>
        <div className="toolbar">
          <input
            className="input"
            placeholder="Название нового проекта"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create.mutate()}
            style={{ flex: 1 }}
          />
          <Button onClick={() => create.mutate()} disabled={create.isPending}>
            Создать
          </Button>
        </div>
      </Card>

      {isLoading && <p className="muted">{t("common.loading")}</p>}
      {isError && <p className="error">{t("auth.genericError")}</p>}
      {data && data.length === 0 && <p className="muted">{t("projects.empty")}</p>}
      {data && data.length > 0 && (
        <div className="list">
          {data.map((p) => (
            <div className="list-item" key={p.id}>
              <button className="link-btn" style={{ fontWeight: 600, fontSize: 15 }}
                      onClick={() => navigate(`/projects/${p.id}`)}>
                {p.name}
              </button>
              <div className="actions">
                <span className="muted">
                  {t("projects.created")} {new Date(p.created_at).toLocaleDateString("ru-RU")}
                </span>
                <Button variant="ghost" onClick={() => remove.mutate(p.id)}>Удалить</Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
