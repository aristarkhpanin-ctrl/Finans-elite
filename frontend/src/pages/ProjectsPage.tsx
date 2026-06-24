import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  createProject,
  createProjectFromTemplate,
  deleteProject,
  listProjects,
  listTemplates,
} from "../api/projects";
import { Button, Card, ErrorState, Loading } from "../components/ui";

export function ProjectsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");

  const { data, isLoading, isError } = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const { data: templates } = useQuery({ queryKey: ["templates"], queryFn: listTemplates });

  const create = useMutation({
    mutationFn: () => createProject(name.trim() || "Новый проект"),
    onSuccess: (p) => {
      setName("");
      qc.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/projects/${p.id}`);
    },
  });

  const fromTemplate = useMutation({
    mutationFn: (tpl: { id: string; name: string }) =>
      createProjectFromTemplate(tpl.id, name.trim() || tpl.name),
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
            Создать пустой
          </Button>
        </div>
        {templates && templates.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
              …или начните с готового шаблона:
            </div>
            <div className="template-grid">
              {templates.map((tpl) => (
                <button key={tpl.id} className="template-card"
                        disabled={fromTemplate.isPending}
                        onClick={() => fromTemplate.mutate({ id: tpl.id, name: tpl.name })}>
                  <span className="template-name">{tpl.name}</span>
                  <span className="template-desc">{tpl.description}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {isLoading && <Loading />}
      {isError && <ErrorState text="Не удалось загрузить проекты." />}
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
