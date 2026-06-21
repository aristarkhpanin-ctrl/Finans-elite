import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MonteCarloTab } from "./analysis/MonteCarloTab";
import { SensitivityTab } from "./analysis/SensitivityTab";
import { WhatIfTab } from "./analysis/WhatIfTab";

const TABS = [
  ["sensitivity", "Чувствительность"],
  ["montecarlo", "Монте-Карло"],
  ["whatif", "What-If"],
] as const;

export function ProjectAnalysisPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState<string>("sensitivity");

  return (
    <div>
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <button className="link-btn" onClick={() => navigate(`/projects/${id}`)}>← Редактор</button>
        <span style={{ flex: 1 }} />
        <button className="link-btn" onClick={() => navigate(`/projects/${id}/results`)}>Результаты →</button>
      </div>
      <h1>Анализ проекта</h1>

      <div className="tabs">
        {TABS.map(([key, label]) => (
          <button key={key} className={`tab ${tab === key ? "tab--active" : ""}`} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "sensitivity" && <SensitivityTab projectId={id} />}
      {tab === "montecarlo" && <MonteCarloTab projectId={id} />}
      {tab === "whatif" && <WhatIfTab projectId={id} />}
    </div>
  );
}
