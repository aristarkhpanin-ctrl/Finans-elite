import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { runWhatIf, SENSITIVITY_PARAMS, type ScenarioIn } from "../../api/analysis";
import { ESelect } from "../../components/EditorField";
import { IconTrash } from "../../components/icons";
import { Button, Modal, Switch } from "../../components/ui";
import { fmtMillions, fmtRatio, percent } from "../../format";

const paramLabel = (p: string) => SENSITIVITY_PARAMS.find(([k]) => k === p)?.[1] ?? p;
const fmtK = (v: string) => "×" + Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 2 });

const newScenario = (n: number): ScenarioIn => ({
  name: `Сценарий ${n}`,
  adjustments: [{ param: "sales_price", factor: "1.1" }],
});

export function WhatIfTab({ projectId }: { projectId: string }) {
  const [scenarios, setScenarios] = useState<ScenarioIn[]>([newScenario(1)]);
  const [includeBase, setIncludeBase] = useState(true);
  const [editIdx, setEditIdx] = useState<number | null>(null);
  const [draft, setDraft] = useState<ScenarioIn | null>(null);

  const run = useMutation({ mutationFn: () => runWhatIf(projectId, scenarios, includeBase) });
  const d = run.data;

  const openEditor = (i: number) => {
    setEditIdx(i);
    setDraft(JSON.parse(JSON.stringify(scenarios[i])));
  };
  const saveDraft = () => {
    if (editIdx === null || !draft) return;
    setScenarios(scenarios.map((s, k) => (k === editIdx ? draft : s)));
    setEditIdx(null);
    setDraft(null);
  };

  // Лучший / худший по NPV для подсветки.
  const npvs = d?.scenarios.map((s) => Number(s.npv)) ?? [];
  const bestNpv = npvs.length ? Math.max(...npvs) : 0;
  const worstNpv = npvs.length ? Math.min(...npvs) : 0;
  const maxAbs = Math.max(1, ...npvs.map(Math.abs));

  return (
    <div>
      <div className="an-head">
        <div style={{ minWidth: 0 }}>
          <div className="an-head__title">What-If · сценарии</div>
          <div className="an-head__sub">
            Корректировки параметров → сравнение ключевых показателей по сценариям.
          </div>
        </div>
        <Switch label="Включая базовый" checked={includeBase} onChange={setIncludeBase} />
      </div>

      <div className="scn-list">
        {scenarios.map((s, i) => (
          <div className="scn-row" key={i}>
            <div className="scn-handle">{i + 1}</div>
            <div className="scn-name">{s.name}</div>
            <div className="scn-adj">
              {s.adjustments.length === 0 ? (
                <span className="scn-noadj">без корректировок</span>
              ) : (
                s.adjustments.map((a, k) => (
                  <span key={k} className="scn-chip">
                    {paramLabel(a.param)} {fmtK(a.factor)}
                  </span>
                ))
              )}
            </div>
            <button type="button" className="scn-edit" onClick={() => openEditor(i)}>
              Изменить
            </button>
            <button
              type="button"
              className="scn-del"
              title="Удалить сценарий"
              onClick={() => setScenarios(scenarios.filter((_, k) => k !== i))}
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          className="add-row"
          onClick={() => setScenarios([...scenarios, newScenario(scenarios.length + 1)])}
        >
          ＋&nbsp;&nbsp;Добавить сценарий
        </button>
      </div>

      <Button loading={run.isPending} onClick={() => run.mutate()}>
        {run.isPending ? "Сравнение…" : "Сравнить"}
      </Button>

      {run.isError && (
        <div className="an-err" style={{ marginTop: 16 }}>
          <div className="an-err__ico">!</div>
          <div style={{ minWidth: 0 }}>
            <div className="an-err__title">Не удалось сравнить сценарии</div>
            <div className="an-err__sub">
              {(run.error as any)?.response?.data?.detail ?? "Проверьте корректировки и повторите."}
            </div>
            <Button variant="ghost" onClick={() => run.mutate()}>
              Повторить
            </Button>
          </div>
        </div>
      )}

      {d && (
        <>
          <div className="terms-head" style={{ marginTop: 20 }}>
            Сравнение сценариев
          </div>
          <div className="cmp-tbl fe-scroll">
            <div className="cmp-row cmp-row--head">
              <div className="cmp-col-name">Сценарий</div>
              <div className="cmp-col-bar">NPV</div>
              <div className="cmp-col-num">NPV, млн</div>
              <div className="cmp-col-num">IRR</div>
              <div className="cmp-col-num">PI</div>
              <div className="cmp-col-num">Окуп.</div>
            </div>
            {d.scenarios.map((s, i) => {
              const npv = Number(s.npv);
              const best = d.scenarios.length > 1 && npv === bestNpv;
              const worst = d.scenarios.length > 1 && npv === worstNpv && !best;
              return (
                <div
                  key={i}
                  className={"cmp-row" + (best ? " cmp-row--best" : worst ? " cmp-row--worst" : "")}
                >
                  <div className="cmp-col-name">
                    <span className="cmp-tag">{String.fromCharCode(65 + i)}</span>
                    {s.name}
                  </div>
                  <div className="cmp-col-bar">
                    <div className="profile-track">
                      <div
                        className="profile-fill"
                        style={{
                          width: `${(Math.abs(npv) / maxAbs) * 100}%`,
                          background: npv < 0 ? "var(--danger)" : "var(--primary)",
                        }}
                      />
                    </div>
                  </div>
                  <div className="cmp-col-num" style={{ color: npv < 0 ? "var(--danger)" : "var(--text)" }}>
                    {fmtMillions(s.npv, { digits: 1 })}
                  </div>
                  <div className="cmp-col-num">{s.irr_annual ? percent(s.irr_annual, 1) : "—"}</div>
                  <div className="cmp-col-num">{s.pi ? fmtRatio(s.pi, 2) : "—"}</div>
                  <div className="cmp-col-num">{s.pb_months != null ? `${s.pb_months} мес` : "—"}</div>
                </div>
              );
            })}
          </div>
          <div className="cmp-legend">
            <span>
              <span className="cmp-legend__sw" style={{ background: "var(--good)" }} />
              лучший по NPV
            </span>
            <span>
              <span className="cmp-legend__sw" style={{ background: "var(--danger)" }} />
              худший по NPV
            </span>
          </div>
        </>
      )}

      {/* C3: редактор сценария */}
      <Modal
        open={editIdx !== null && draft !== null}
        onClose={() => {
          setEditIdx(null);
          setDraft(null);
        }}
        title="Сценарий"
        sub="Название и корректировки параметров (множители к базовым значениям)."
        maxWidth={480}
        actions={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setEditIdx(null);
                setDraft(null);
              }}
            >
              Отмена
            </Button>
            <Button onClick={saveDraft}>Сохранить</Button>
          </>
        }
      >
        {draft && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="field" style={{ marginBottom: 0 }}>
              <label>Название сценария</label>
              <input
                className="input"
                value={draft.name}
                autoFocus
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </div>

            <div className="terms-head" style={{ margin: "2px 0 0" }}>
              Корректировки
            </div>
            {draft.adjustments.map((a, k) => (
              <div key={k} style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <ESelect
                    label=""
                    value={a.param}
                    onChange={(v) =>
                      setDraft({
                        ...draft,
                        adjustments: draft.adjustments.map((x, j) => (j === k ? { ...x, param: v } : x)),
                      })
                    }
                    options={SENSITIVITY_PARAMS}
                  />
                </div>
                <div style={{ width: 96 }}>
                  <div className="efield__box">
                    <span className="efield__prefix">×</span>
                    <input
                      className="efield__input"
                      inputMode="decimal"
                      value={a.factor}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          adjustments: draft.adjustments.map((x, j) =>
                            j === k ? { ...x, factor: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </div>
                </div>
                <button
                  type="button"
                  className="scn-del"
                  title="Удалить корректировку"
                  onClick={() =>
                    setDraft({ ...draft, adjustments: draft.adjustments.filter((_, j) => j !== k) })
                  }
                >
                  <IconTrash size={15} />
                </button>
              </div>
            ))}
            <button
              type="button"
              className="add-row"
              style={{ height: 40 }}
              onClick={() =>
                setDraft({ ...draft, adjustments: [...draft.adjustments, { param: "direct_costs", factor: "0.9" }] })
              }
            >
              ＋&nbsp;&nbsp;Добавить корректировку
            </button>
          </div>
        )}
      </Modal>
    </div>
  );
}
