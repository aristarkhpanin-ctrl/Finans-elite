import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { ProjectModel } from "../api/model";
import { httpDetail, httpFieldError, httpStatus } from "../api/client";
import { createProjectFromModel, getProject, updateProject } from "../api/projects";
import { EditConflictModal, useEditConflict } from "../components/EditConflict";
import { useToast } from "../components/Toast";
import { Button, ErrorState, Loading } from "../components/ui";
import { UnsavedLeaveModal, useUnsavedGuard } from "../components/UnsavedGuard";
import { ValidationPanel } from "../components/ValidationPanel";
import { ActualizationTab } from "./editor/ActualizationTab";
import { AssetsTab } from "./editor/AssetsTab";
import { CalendarTab } from "./editor/CalendarTab";
import { CostsTab } from "./editor/CostsTab";
import { CurrencyTab } from "./editor/CurrencyTab";
import { DocumentTab } from "./editor/DocumentTab";
import { FinancingTab } from "./editor/FinancingTab";
import { GeneralTab } from "./editor/GeneralTab";
import { SalesTab } from "./editor/SalesTab";
import { TablesTab } from "./editor/TablesTab";

const TABS = [
  ["general", "Проект"],
  ["sales", "Сбыт"],
  ["costs", "Издержки"],
  ["assets", "Инвестиции"],
  ["calendar", "Календарный план"],
  ["financing", "Финансирование"],
  ["currency", "Валюта и старт"],
  ["tables", "Таблицы"],
  ["document", "Документ"],
  ["actual", "Факт"],
] as const;

type TabKey = (typeof TABS)[number][0];

/** Бейджи количества на вкладках (продукты/статьи/активы/источники/факт-месяцы). */
function tabBadge(model: ProjectModel, tab: TabKey): number {
  switch (tab) {
    case "sales":
      return model.operating_plan.sales.length;
    case "costs":
      return (
        model.operating_plan.direct_costs.length +
        model.operating_plan.fixed_costs.length +
        (model.operating_plan.staff?.length ?? 0)
      );
    case "assets":
      return model.investment_plan.assets.length;
    case "calendar":
      return model.investment_plan.calendar?.stages.length ?? 0;
    case "tables":
      return model.user_tables?.length ?? 0;
    case "document":
      return model.business_plan?.length ?? 0;
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
  const savedSnapshot = useRef<string>("");
  // Ревизия той версии, которую правим (G2). Сервер сверяет её при сохранении: если
  // проект с тех пор сохранил кто-то другой, он ответит 409, а не сотрёт чужие правки.
  const revision = useRef<string>("");
  const conflict = useEditConflict();
  const [resolving, setResolving] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (data) {
      setModel(data.model);
      savedSnapshot.current = JSON.stringify(data.model);
      revision.current = data.revision ?? "";
    }
  }, [data]);

  const save = useMutation({
    mutationFn: () => updateProject(id, model!.header.name, model!, revision.current),
    onSuccess: (saved) => {
      savedSnapshot.current = JSON.stringify(model);
      revision.current = saved.revision ?? "";
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (e) => { conflict.catchConflict(e); },
  });

  const dirty = model != null && JSON.stringify(model) !== savedSnapshot.current;

  // Страж несохранённого ввода — общий с «Финанс-Аудитом» (components/UnsavedGuard).
  const { tryNav, pending: pendingLeave, cancel: cancelLeave } = useUnsavedGuard(dirty);

  if (isError) return <ErrorState text="Не удалось загрузить проект." />;
  if (isLoading || !model) return <Loading />;

  const n = model.header.duration_months;

  const discard = () => {
    setModel(JSON.parse(savedSnapshot.current));
    save.reset();
  };

  const calcAndGo = async () => {
    try {
      if (dirty || save.isError) await save.mutateAsync();
    } catch {
      return;   // причина уже на экране: статус сохранения или модалка конфликта
    }
    navigate(`/projects/${id}/results`);
  };

  /** Свои правки — в новый проект: ничьи правки не пропадают (G2). */
  const saveCopy = async () => {
    setResolving(true);
    try {
      const copy = await createProjectFromModel(`${model.header.name} — мои правки`, model);
      conflict.close();
      save.reset();
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast("Ваши правки сохранены новым проектом", { kind: "success" });
      navigate(`/projects/${copy.id}`);
    } catch (e) {
      toast(httpDetail(e) ?? "Не удалось создать проект", { kind: "error" });
    } finally {
      setResolving(false);
    }
  };

  /** Открыть сохранённую другим версию — свои несохранённые правки пропадают. */
  const takeTheirs = async () => {
    setResolving(true);
    try {
      const fresh = await getProject(id);
      qc.setQueryData(["project", id], fresh);
      setModel(fresh.model);
      savedSnapshot.current = JSON.stringify(fresh.model);
      revision.current = fresh.revision ?? "";
      save.reset();
      conflict.close();
    } catch (e) {
      toast(httpDetail(e) ?? "Не удалось загрузить проект", { kind: "error" });
    } finally {
      setResolving(false);
    }
  };

  /**
   * Сохранить свои правки поверх — осознанно, после второго нажатия в модалке. Ревизия
   * берётся свежая: иначе сервер снова ответил бы тем же конфликтом.
   */
  const overwrite = async () => {
    setResolving(true);
    try {
      revision.current = (await getProject(id)).revision ?? "";
      conflict.close();
      await save.mutateAsync();
    } catch {
      // новый конфликт или ошибка сохранения уже показаны тем же путём, что обычно
    } finally {
      setResolving(false);
    }
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
          environment={model.environment}
          onHeader={(header) => setModel({ ...model, header })}
          onSettings={(settings) => setModel({ ...model, settings })}
          onEnvironment={(environment) => setModel({ ...model, environment })}
        />
      )}
      {tab === "sales" && (
        <SalesTab n={n} operating={model.operating_plan} company={model.company}
                  onChange={(operating_plan) => setModel({ ...model, operating_plan })}
                  onCompany={(company) => setModel({ ...model, company })} />
      )}
      {tab === "costs" && (
        <CostsTab n={n} operating={model.operating_plan}
                  onChange={(operating_plan) => setModel({ ...model, operating_plan })} />
      )}
      {tab === "assets" && (
        <AssetsTab investment={model.investment_plan}
                   onChange={(investment_plan) => setModel({ ...model, investment_plan })} />
      )}
      {tab === "calendar" && (
        <CalendarTab n={n} startDate={model.header.start_date} investment={model.investment_plan}
                     products={model.operating_plan.products}
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
      {tab === "tables" && (
        <TablesTab tables={model.user_tables ?? []}
                   onChange={(user_tables) => setModel({ ...model, user_tables })} />
      )}
      {tab === "document" && (
        <DocumentTab sections={model.business_plan ?? []}
                     onChange={(business_plan) => setModel({ ...model, business_plan })} />
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
              {/* Отказ по одному полю называет это поле: искать виновную ячейку
                  глазами по всей модели — не работа пользователя. */}
              <span className="save-text--err" title={httpFieldError(save.error) ?? ""}>
                {httpStatus(save.error) === 409
                  ? "Проект сохранил кто-то другой · правки не записаны"
                  : httpFieldError(save.error) ?? "Не удалось сохранить · повторите"}
              </span>
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

      <UnsavedLeaveModal pending={pendingLeave} saving={saving} onCancel={cancelLeave}
                         onSave={async () => { await save.mutateAsync(); }} />
      <EditConflictModal kind="project" open={conflict.open} detail={conflict.detail}
                         busy={resolving} onClose={conflict.close} onSaveCopy={saveCopy}
                         onTakeTheirs={takeTheirs} onOverwrite={overwrite} />
    </div>
  );
}
