import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getProject } from "../api/projects";
import { MethodologyTab } from "./analysis/MethodologyTab";
import { MonteCarloTab } from "./analysis/MonteCarloTab";
import { ReviewTab } from "./analysis/ReviewTab";
import { SensitivityTab } from "./analysis/SensitivityTab";
import { VersionsTab } from "./analysis/VersionsTab";
import { WhatIfTab } from "./analysis/WhatIfTab";
import { usePageTitle } from "../pageTitle";

const TABS = [
  ["review", "Ревью плана", "находки и гейт"],
  ["sensitivity", "Чувствительность", "NPV к параметру"],
  ["montecarlo", "Монте-Карло", "распределение NPV"],
  ["whatif", "What-If", "сравнение сценариев"],
  ["versions", "Версии", "снимки и изменения"],
  ["methodology", "Методика", "трактовки расчёта"],
] as const;

export function ProjectAnalysisPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState<string>("review");
  const projectQuery = useQuery({ queryKey: ["project", id], queryFn: () => getProject(id) });
  const name = projectQuery.data?.name ?? "";
  usePageTitle("Анализ", name);

  return (
    <div>
      <div className="esub">
        <div className="esub__top">
          <div className="esub__left">
            <button type="button" className="back-btn" onClick={() => navigate(`/projects/${id}`)}>
              ←<span style={{ marginLeft: 6 }}>Редактор</span>
            </button>
            <h1 className="sr-only">Анализ рисков проекта «{name || "…"}»</h1>
            {name && (
              <span className="subheader__title" style={{ maxWidth: 320 }}>
                {name}
              </span>
            )}
            <span className="status-chip status-chip--info">Анализ рисков</span>
          </div>
          {/* Обёртка `esub__actions` — как у редактора: на телефоне она уходит своей
              строкой. Без неё переключатель делил строку с кнопкой «назад» и ложился
              поверх неё, а название проекта пропадало (матрица P13, G15). */}
          <div className="esub__actions">
            <div className="mode-seg">
              <button type="button" className="mode-seg__btn" onClick={() => navigate(`/projects/${id}`)}>
                Редактор
              </button>
              <button type="button" className="mode-seg__btn" onClick={() => navigate(`/projects/${id}/results`)}>
                Результаты
              </button>
              <button type="button" className="mode-seg__btn mode-seg__btn--active" aria-current="page">
                Анализ
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="etabs-wrap">
        <div className="etabs fe-scroll">
          {TABS.map(([key, label, sub]) => (
            <button
              aria-pressed={tab === key}
              key={key}
              type="button"
              className={"etab atab" + (tab === key ? " etab--active atab--active" : "")}
              onClick={() => setTab(key)}
            >
              <span>{label}</span>
              <span className="atab__sub">{sub}</span>
            </button>
          ))}
        </div>
      </div>

      {tab === "review" && <ReviewTab projectId={id} />}
      {tab === "sensitivity" && <SensitivityTab projectId={id} />}
      {tab === "montecarlo" && <MonteCarloTab projectId={id} />}
      {tab === "whatif" && <WhatIfTab projectId={id} />}
      {tab === "versions" && <VersionsTab projectId={id} />}
      {tab === "methodology" && <MethodologyTab projectId={id} />}
    </div>
  );
}
