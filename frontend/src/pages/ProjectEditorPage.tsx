import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { ProjectModel } from "../api/model";
import { getProject, updateProject } from "../api/projects";
import { IconWarning } from "../components/icons";
import { Button, ErrorState, Loading, Modal } from "../components/ui";
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

type TabKey = (typeof TABS)[number][0];

/** Бейджи количества на вкладках (продукты/статьи/активы/источники/факт-месяцы). */
function tabBadge(model: ProjectModel, tab: TabKey): number {
  switch (tab) {
    case "sales":
      return model.operating_plan.sales.length;
    case "costs":
      return model.operating_plan.direct_costs.length + model.operating_plan.fixed_costs.length;
    case "assets":
      return model.investment_plan.assets.length;
    case "financing":
      return (
        model.financing.loans.length +
        (model.financing.leases?.length ?? 0) +
        (model.financing.deposits?.length ?? 0) +
        model.financing.equity.length
      );
    case "actual":
      return model.actualization.actual_until;
    default:
      return 0;
  }
}

export function ProjectEditorPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { data, isLoading, isError } = useQuery({ queryKey: ["project", id], queryFn: () => getProject(id) });

  const [model, setModel] = useState<ProjectModel | null>(null);
  const [tab, setTab] = useState<TabKey>(() => {
    // ?tab=currency — прямой переход на вкладку (например, из ошибки расчёта)
    const t = searchParams.get("tab");
    return TABS.some(([k]) => k === t) ? (t as TabKey) : "general";
  });
  const [pendingLeave, setPendingLeave] = useState<{ label: string; go: () => void } | null>(null);
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

  if (isError) return <ErrorState text="Не удалось загрузить проект." />;
  if (isLoading || !model) return <Loading />;

  const n = model.header.duration_months;

  /** Переход с guard несохранённых изменений. */
  const tryNav = (label: string, go: () => void) => {
    if (dirty) setPendingLeave({ label, go });
    else go();
  };

  const discard = () => {
    setModel(JSON.parse(savedSnapshot.current));
    save.reset();
  };

  const calcAndGo = async () => {
    if (dirty || save.isError) await save.mutateAsync();
    navigate(`/projects/${id}/results`);
  };

  const saving = save.isPending;
  const saveErr = save.isError && !saving;
  const dirtyIdle = dirty && !saving && !saveErr;
  const savedClean = !dirty && !saving && !saveErr;

  return (
    <div>
      <div className="esub">
        <div className="esub__top">
          <div className="esub__left">
            <button type="button" className="back-btn" onClick={() => tryNav("Проекты", () => navigate("/projects"))}>
              ←<span style={{ marginLeft: 6 }}>Проекты</span>
            </button>
            <div className="name-wrap" title="Переименовать проект">
              <input
                value={model.header.name}
                placeholder="Без названия"
                onChange={(e) => setModel({ ...model, header: { ...model.header, name: e.target.value } })}
              />
              <span className="name-wrap__ico">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M4 20h4L19 9l-4-4L4 16v4z" strokeLinejoin="round" />
                </svg>
              </span>
            </div>
          </div>
          <div className="esub__actions">
            <div className="mode-seg">
              <button type="button" className="mode-seg__btn mode-seg__btn--active">
                Редактор
              </button>
              <button
                type="button"
                className="mode-seg__btn"
                onClick={() => tryNav("Результаты", () => navigate(`/projects/${id}/results`))}
              >
                Результаты
              </button>
              <button
                type="button"
                className="mode-seg__btn"
                onClick={() => tryNav("Анализ", () => navigate(`/projects/${id}/analysis`))}
              >
                Анализ
              </button>
            </div>
            <Button loading={saving} onClick={() => void calcAndGo()}>
              Рассчитать →
            </Button>
          </div>
        </div>

        <ValidationPanel model={model} />
      </div>

      <div className="etabs-wrap">
        <div className="etabs fe-scroll">
          {TABS.map(([key, label]) => {
            const badge = tabBadge(model, key);
            return (
              <button
                key={key}
                type="button"
                className={"etab" + (tab === key ? " etab--active" : "")}
                onClick={() => setTab(key)}
              >
                <span>{label}</span>
                {badge > 0 && <span className="etab__badge">{badge}</span>}
              </button>
            );
          })}
        </div>
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
        <div className="save-bar__status">
          {saving && (
            <>
              <span className="save-spinner" />
              <span className="save-text--saving">Сохранение…</span>
            </>
          )}
          {saveErr && (
            <>
              <span className="save-err-dot">!</span>
              <span className="save-text--err">Не удалось сохранить · повторите</span>
            </>
          )}
          {dirtyIdle && (
            <>
              <span className="save-dirty-dot" />
              <span className="save-text--dirty">Несохранённые изменения</span>
            </>
          )}
          {savedClean && (
            <>
              <span className="save-check">✓</span>
              <span className="save-text--saved">Все изменения сохранены</span>
            </>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {(dirty || saveErr) && !saving && (
            <Button variant="ghost" onClick={discard}>
              Отменить
            </Button>
          )}
          <Button disabled={savedClean} loading={saving} onClick={() => save.mutate()}>
            Сохранить
          </Button>
        </div>
      </div>

      <Modal open={!!pendingLeave} onClose={() => setPendingLeave(null)} maxWidth={420}>
        <div style={{ textAlign: "center" }}>
          <div className="modal-warn-ico">
            <IconWarning size={22} />
          </div>
          <h3 className="modal__title">Несохранённые изменения</h3>
          <div className="modal__sub">
            В модели есть изменения, которые ещё не сохранены. Сохранить их перед переходом в «
            {pendingLeave?.label}»?
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
            <Button
              loading={saving}
              onClick={async () => {
                const go = pendingLeave!.go;
                await save.mutateAsync();
                setPendingLeave(null);
                go();
              }}
            >
              Сохранить и выйти
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                const go = pendingLeave!.go;
                setPendingLeave(null);
                go();
              }}
            >
              Выйти без сохранения
            </Button>
            <Button variant="link" style={{ alignSelf: "center" }} onClick={() => setPendingLeave(null)}>
              Отмена
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
