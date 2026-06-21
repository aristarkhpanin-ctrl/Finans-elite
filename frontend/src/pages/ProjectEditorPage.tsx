import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { ProjectModel } from "../api/model";
import { getProject, updateProject } from "../api/projects";
import { Button } from "../components/ui";
import { AssetsTab } from "./editor/AssetsTab";
import { CostsTab } from "./editor/CostsTab";
import { FinancingTab } from "./editor/FinancingTab";
import { GeneralTab } from "./editor/GeneralTab";
import { SalesTab } from "./editor/SalesTab";

const TABS = [
  ["general", "Проект"],
  ["sales", "Сбыт"],
  ["costs", "Издержки"],
  ["assets", "Инвестиции"],
  ["financing", "Финансирование"],
] as const;

export function ProjectEditorPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({ queryKey: ["project", id], queryFn: () => getProject(id) });

  const [model, setModel] = useState<ProjectModel | null>(null);
  const [tab, setTab] = useState<string>("general");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) setModel(data.model);
  }, [data]);

  const save = useMutation({
    mutationFn: () => updateProject(id, model!.header.name, model!),
    onSuccess: () => {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  if (isLoading || !model) return <p className="muted">Загрузка…</p>;
  if (isError) return <p className="error">Не удалось загрузить проект</p>;

  const n = model.header.duration_months;

  return (
    <div>
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <button className="link-btn" onClick={() => navigate("/projects")}>← Проекты</button>
        <span style={{ flex: 1 }} />
        <button className="link-btn" onClick={async () => { await save.mutateAsync(); navigate(`/projects/${id}/analysis`); }}>
          Анализ
        </button>
        <Button
          variant="ghost"
          onClick={async () => {
            await save.mutateAsync();
            navigate(`/projects/${id}/results`);
          }}
        >
          Рассчитать →
        </Button>
      </div>
      <h1>{model.header.name}</h1>

      <div className="tabs">
        {TABS.map(([key, label]) => (
          <button key={key} className={`tab ${tab === key ? "tab--active" : ""}`} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "general" && (
        <GeneralTab
          header={model.header}
          settings={model.settings}
          onHeader={(header) => setModel({ ...model, header })}
          onSettings={(settings) => setModel({ ...model, settings })}
        />
      )}
      {tab === "sales" && (
        <SalesTab n={n} operating={model.operating_plan}
                  onChange={(operating_plan) => setModel({ ...model, operating_plan })} />
      )}
      {tab === "costs" && (
        <CostsTab n={n} operating={model.operating_plan}
                  onChange={(operating_plan) => setModel({ ...model, operating_plan })} />
      )}
      {tab === "assets" && (
        <AssetsTab investment={model.investment_plan}
                   onChange={(investment_plan) => setModel({ ...model, investment_plan })} />
      )}
      {tab === "financing" && (
        <FinancingTab financing={model.financing}
                      onChange={(financing) => setModel({ ...model, financing })} />
      )}

      <div className="save-bar">
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Сохранение…" : "Сохранить"}
        </Button>
        {saved && <span style={{ color: "var(--success)" }}>Сохранено ✓</span>}
        {save.isError && <span className="error">Ошибка сохранения</span>}
      </div>
    </div>
  );
}
