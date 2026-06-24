import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { ProjectModel } from "../api/model";
import { getProject, updateProject } from "../api/projects";
import { Button, ErrorState, Loading } from "../components/ui";
import { ValidationPanel } from "../components/ValidationPanel";
import { ActualizationTab } from "./editor/ActualizationTab";
import { AssetsTab } from "./editor/AssetsTab";
import { CostsTab } from "./editor/CostsTab";
import { CurrencyTab } from "./editor/CurrencyTab";
import { FinancingTab } from "./editor/FinancingTab";
import { GeneralTab } from "./editor/GeneralTab";
import { SalesTab } from "./editor/SalesTab";

const TABS = [
  ["general", "Проект"],
  ["sales", "Сбыт"],
  ["costs", "Издержки"],
  ["assets", "Инвестиции"],
  ["financing", "Финансирование"],
  ["currency", "Валюта и старт"],
  ["actual", "Факт"],
] as const;

export function ProjectEditorPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({ queryKey: ["project", id], queryFn: () => getProject(id) });

  const [model, setModel] = useState<ProjectModel | null>(null);
  const [tab, setTab] = useState<string>("general");
  const [saved, setSaved] = useState(false);
  const savedSnapshot = useRef<string>("");

  useEffect(() => {
    if (data) {
      setModel(data.model);
      savedSnapshot.current = JSON.stringify(data.model);
    }
  }, [data]);

  const save = useMutation({
    mutationFn: () => updateProject(id, model!.header.name, model!),
    onSuccess: () => {
      savedSnapshot.current = JSON.stringify(model);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const dirty = model != null && JSON.stringify(model) !== savedSnapshot.current;

  // Предупреждение о несохранённых изменениях при закрытии/перезагрузке вкладки.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  if (isLoading || !model) return <Loading />;
  if (isError) return <ErrorState text="Не удалось загрузить проект." />;

  const n = model.header.duration_months;

  return (
    <div>
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <button className="link-btn" onClick={() => {
          if (!dirty || window.confirm("Есть несохранённые изменения. Уйти без сохранения?")) navigate("/projects");
        }}>← Проекты</button>
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

      <ValidationPanel model={model} />

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
        <FinancingTab n={n} financing={model.financing}
                      onChange={(financing) => setModel({ ...model, financing })} />
      )}
      {tab === "currency" && (
        <CurrencyTab n={n} environment={model.environment} company={model.company}
                     onEnvironment={(environment) => setModel({ ...model, environment })}
                     onCompany={(company) => setModel({ ...model, company })} />
      )}
      {tab === "actual" && (
        <ActualizationTab n={n} actualization={model.actualization}
                          onChange={(actualization) => setModel({ ...model, actualization })} />
      )}

      <div className="save-bar">
        <Button onClick={() => save.mutate()} disabled={save.isPending || !dirty}>
          {save.isPending ? "Сохранение…" : "Сохранить"}
        </Button>
        {dirty && !save.isPending && <span className="muted">● несохранённые изменения</span>}
        {saved && <span style={{ color: "var(--success)" }}>Сохранено ✓</span>}
        {save.isError && <span className="error">Ошибка сохранения</span>}
      </div>
    </div>
  );
}
