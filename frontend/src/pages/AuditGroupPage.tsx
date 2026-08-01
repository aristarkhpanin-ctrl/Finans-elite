import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  RATIO_GROUPS,
  analyzeAuditGroup,
  consolidateAudit,
  createAuditGroup,
  deleteAuditGroup,
  getAuditGroup,
  listAuditGroups,
  listAuditSubjects,
  updateAuditGroup,
  type AuditConsolidation,
  type AuditElimination,
  type AuditGroupModel,
} from "../api/audit";
import { IconBriefcase, IconDownload, IconTrash } from "../components/icons";
import { useToast } from "../components/Toast";
import { Button } from "../components/ui";
import { downloadAuditXlsx } from "../auditExport";

const dec = (v: string | null | undefined): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const x = Number(String(v).replace(",", "."));
  return Number.isFinite(x) ? x : null;
};
const fmtNum = (v: string | null | undefined, digits = 2): string => {
  const x = dec(v);
  return x === null ? "—" : x.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
};
const PCT_RATIOS = /^(Рентабельность|Коэффициент автономии|Суммарные обязательства)/;
const MONEY_RATIOS = /^(Чистый оборотный капитал)/;
const fmtRatio = (name: string, v: string | null): string => {
  const x = dec(v);
  if (x === null) return "—";
  if (MONEY_RATIOS.test(name)) return fmtNum(v, 0);
  if (PCT_RATIOS.test(name)) return (x * 100).toFixed(1).replace(".", ",") + "%";
  return fmtNum(v);
};

type ElimKey = keyof AuditElimination;

/**
 * Виды внутригрупповых величин: поле → подпись и что с чем вычитается парно (пара по обе
 * стороны баланса — то, из-за чего свод остаётся сходящимся).
 */
const ELIM_KINDS: [ElimKey, string, string][] = [
  ["receivables", "Взаимная задолженность",
   "вычитается из дебиторской и из кредиторской задолженности"],
  ["revenue", "Взаимная выручка",
   "вычитается из выручки и из себестоимости покупателя"],
  ["investments", "Вложения в капитал участников",
   "доли участия: вычитаются из внеоборотных активов и из капитала"],
  ["unrealized_profit", "Нереализованная прибыль в запасах",
   "наценка по внутренней продаже: из запасов и из капитала, себестоимость восстанавливается"],
];

/**
 * Консолидация группы предприятий (Финанс-Аудит, фаза H): выбор субъектов → свод →
 * анализ группы как единого предприятия. Внутригрупповые обороты вычитаются, только если
 * заданы явно; иначе выводится оговорка о завышении показателей группы.
 */
export function AuditGroupPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const { data: subjects, isLoading } = useQuery({
    queryKey: ["audit-subjects"],
    queryFn: listAuditSubjects,
  });
  const { data: groups } = useQuery({
    queryKey: ["audit-groups"],
    queryFn: listAuditGroups,
  });

  const [selected, setSelected] = useState<string[]>([]);
  const [name, setName] = useState("Группа предприятий");
  const [result, setResult] = useState<AuditConsolidation | null>(null);
  // Открытая сохранённая группа (null — новая) и признак правки формы после открытия.
  const [groupId, setGroupId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  // Имена участников на момент сохранения: единственный след от удалённого субъекта.
  const [savedNames, setSavedNames] = useState<Record<string, string>>({});
  // Внутригрупповые величины к исключению (v2): по одному значению на период свода.
  const [elimOn, setElimOn] = useState(false);
  const [elim, setElim] = useState<Partial<Record<ElimKey, string>>>({});

  const toggle = (id: string) => {
    setDirty(true);
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  };
  const setElimField = (key: ElimKey, value: string) => {
    setDirty(true);
    setElim((e) => ({ ...e, [key]: value }));
  };

  /**
   * Одна сумма распространяется на все периоды свода (частый случай — одинаковый годовой
   * оборот). Ряд отправляется с запасом: сервер обрезает его до числа периодов свода.
   */
  const MAX_PERIODS = 48;   // верхняя граница числа периодов субъекта
  const elimination = (): AuditElimination | undefined => {
    if (!elimOn) return undefined;
    const row = (key: ElimKey) => Array.from({ length: MAX_PERIODS }, () => elim[key] || "0");
    return {
      receivables: row("receivables"),
      revenue: row("revenue"),
      investments: row("investments"),
      unrealized_profit: row("unrealized_profit"),
    };
  };

  /** Участники состава, которых больше нет среди субъектов (показываем явно). */
  const missingSelected = selected.filter((id) => !(subjects ?? []).some((s) => s.id === id));
  const liveSelected = selected.filter((id) => !missingSelected.includes(id));

  /**
   * Сохранённая группа без правок сводится своим эндпоинтом — он сам разбирается с
   * выбывшими участниками и называет их в оговорках. Правленая форма (или новая группа)
   * сводится разово по живым субъектам: выбывшие показаны отдельным предупреждением, так
   * что из свода они не исчезают молча.
   */
  const run = useMutation({
    mutationFn: () => (groupId && !dirty
      ? analyzeAuditGroup(groupId)
      : consolidateAudit(liveSelected, name, elimination())),
    onSuccess: (r) => { setResult(r); toast("Свод построен", { kind: "success" }); },
    onError: () => toast("Не удалось построить свод", { kind: "error" }),
  });

  /**
   * Состав для сохранения. Имя участника — «надгробие» на случай удаления субъекта:
   * у живого берём текущее имя, у выбывшего сохраняем прежнее, иначе он превратился бы
   * в безымянный идентификатор и оговорка свода перестала бы его называть.
   */
  const groupModel = (): AuditGroupModel => ({
    members: selected.map((id) => ({
      subject_id: id,
      name: (subjects ?? []).find((s) => s.id === id)?.name ?? savedNames[id] ?? "",
    })),
    elimination: elimination() ?? null,
  });

  const invalidateGroups = () => qc.invalidateQueries({ queryKey: ["audit-groups"] });

  const save = useMutation({
    mutationFn: () => (groupId ? updateAuditGroup(groupId, name, groupModel())
                               : createAuditGroup(name, groupModel())),
    onSuccess: (g) => {
      setGroupId(g.id);
      setDirty(false);
      setSavedNames(Object.fromEntries(g.model.members.map((m) => [m.subject_id, m.name])));
      invalidateGroups();
      toast("Состав группы сохранён", { kind: "success" });
    },
    onError: () => toast("Не удалось сохранить группу", { kind: "error" }),
  });

  /** Открыть сохранённую группу: состав в форму + свод по текущей отчётности участников. */
  const open = useMutation({
    mutationFn: async (id: string) => {
      const group = await getAuditGroup(id);
      return { group, consolidation: await analyzeAuditGroup(id) };
    },
    onSuccess: ({ group, consolidation }) => {
      setGroupId(group.id);
      setDirty(false);
      setName(group.name);
      setSelected(group.model.members.map((m) => m.subject_id));
      setSavedNames(Object.fromEntries(group.model.members.map((m) => [m.subject_id, m.name])));
      const saved = group.model.elimination;
      setElimOn(saved !== null);
      setElim(saved === null ? {} : Object.fromEntries(
        ELIM_KINDS.map(([key]) => [key, saved[key]?.[0] ?? ""])));
      setResult(consolidation);
    },
    onError: () => toast("Не удалось открыть группу", { kind: "error" }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteAuditGroup(id),
    onSuccess: (_r, id) => {
      if (groupId === id) { setGroupId(null); setDirty(false); }
      invalidateGroups();
      toast("Группа удалена", { kind: "success" });
    },
    onError: () => toast("Не удалось удалить группу", { kind: "error" }),
  });

  const a = result?.analysis;

  return (
    <div>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <button type="button" className="link-back" onClick={() => navigate("/audit")}>← К субъектам</button>
          <h1 className="page-title">Консолидация группы</h1>
          <div className="page-sub">
            Свод отчётности нескольких предприятий и анализ группы как единого субъекта.
          </div>
        </div>
      </div>

      {(groups ?? []).length > 0 && (
        <div className="audit-block">
          <div className="audit-block__title">Сохранённые группы</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {(groups ?? []).map((g) => (
              <div className={"opt-row" + (groupId === g.id ? " opt-row--on" : "")} key={g.id}
                   style={{ alignItems: "center" }}>
                <button
                  type="button"
                  disabled={open.isPending}
                  onClick={() => open.mutate(g.id)}
                  style={{ flex: 1, minWidth: 0, textAlign: "left", background: "none",
                           border: "none", padding: 0, font: "inherit", cursor: "pointer" }}
                >
                  <span className="opt-row__label">{g.name}</span>
                  <span className="opt-row__help">
                    участников: {g.n_members}
                    {g.n_missing > 0 && ` · выбыло: ${g.n_missing}`}
                  </span>
                </button>
                <button type="button" className="line-card__del" title="Удалить группу"
                        onClick={() => remove.mutate(g.id)}>
                  <IconTrash size={15} />
                </button>
              </div>
            ))}
          </div>
          <div className="field-note" style={{ marginTop: 10 }}>
            Группа хранит состав, а не числа: свод пересчитывается по текущей отчётности
            участников. Если участника удалили, он назван в оговорках свода — состав
            изменился, и показатели группы уже не те, что были при сохранении.
          </div>
        </div>
      )}

      <div className="audit-block">
        <div className="audit-block__title">Состав группы</div>
        {isLoading ? (
          <div className="page-sub">Загрузка…</div>
        ) : (subjects ?? []).length === 0 ? (
          <div className="page-sub" style={{ fontSize: 12.5 }}>
            Сначала создайте субъекты анализа — из них собирается группа.
          </div>
        ) : (
          <>
            {missingSelected.length > 0 && (
              <div className="field-note field-note--warn" style={{ marginBottom: 12 }}>
                В составе есть участники, которых больше нет — свод считается без них:{" "}
                {missingSelected.map((id, i) => (
                  <span key={id}>
                    {i > 0 && ", "}
                    {savedNames[id] || id}{" "}
                    <button
                      type="button"
                      title="Убрать из состава"
                      onClick={() => { setDirty(true); setSelected((s) => s.filter((x) => x !== id)); }}
                      style={{ background: "none", border: "none", padding: 0,
                               font: "inherit", cursor: "pointer", textDecoration: "underline" }}
                    >
                      убрать
                    </button>
                  </span>
                ))}
                . После правки состава сохраните группу.
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
              {(subjects ?? []).map((s) => (
                <label className="opt-row" key={s.id} style={{ cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    style={{ position: "absolute", opacity: 0, width: 0, height: 0 }}
                    checked={selected.includes(s.id)}
                    onChange={() => toggle(s.id)}
                  />
                  <span className="opt-row__box">{selected.includes(s.id) ? "✓" : ""}</span>
                  <span style={{ minWidth: 0 }}>
                    <span className="opt-row__label">{s.name}</span>
                    <span className="opt-row__help">
                      периодов: {s.n_periods}
                      {!s.balanced && " · баланс не сходится"}
                    </span>
                  </span>
                </label>
              ))}
            </div>
            <label className={"opt-row" + (elimOn ? " opt-row--on" : "")} style={{ cursor: "pointer", marginBottom: 10 }}>
              <input type="checkbox" style={{ position: "absolute", opacity: 0, width: 0, height: 0 }}
                     checked={elimOn}
                     onChange={(e) => { setDirty(true); setElimOn(e.target.checked); }} />
              <span className="opt-row__box">{elimOn ? "✓" : ""}</span>
              <span style={{ minWidth: 0 }}>
                <span className="opt-row__label">Исключить внутригрупповые величины</span>
                <span className="opt-row__help">
                  Каждая вычитается парно по обе стороны баланса, поэтому свод остаётся
                  сходящимся. Суммы указываются за период; лишнее обрезается по остатку
                  строки с оговоркой.
                </span>
              </span>
            </label>
            {elimOn && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 10 }}>
                {ELIM_KINDS.map(([key, label, help]) => (
                  <label className="efield" key={key}>
                    <span className="efield__label">{label}</span>
                    <input className="efield__input" inputMode="decimal"
                           value={elim[key] ?? ""} placeholder="0"
                           onChange={(e) => setElimField(key, e.target.value)} />
                    <span className="field-note">{help}</span>
                  </label>
                ))}
                <div className="field-note">
                  Гудвилл и неконтролирующая доля отдельными статьями не выделяются — в
                  аналитической форме таких строк нет. Вложения вычитаются по балансовой
                  стоимости, поэтому при доле участия менее 100% капитал группы показан по
                  стоимости вложения, а не по чистым активам дочерних компаний.
                </div>
              </div>
            )}
            <div className="ft-row">
              <input className="efield__input" value={name} placeholder="Название группы"
                     onChange={(e) => { setDirty(true); setName(e.target.value); }} />
              <Button variant="ghost" onClick={() => save.mutate()} loading={save.isPending}
                      disabled={selected.length === 0 || (groupId !== null && !dirty)}>
                {groupId ? "Сохранить состав" : "Сохранить группу"}
              </Button>
              <Button onClick={() => run.mutate()} loading={run.isPending}
                      disabled={liveSelected.length === 0 && !(groupId && !dirty)}>
                Построить свод
              </Button>
            </div>
          </>
        )}
      </div>

      {result && a && (
        <>
          {result.warnings.map((w, i) => (
            <div className="field-note field-note--warn" key={i} style={{ marginBottom: 10 }}>{w}</div>
          ))}

          <div className="audit-block">
            <div className="tab-head" style={{ marginBottom: 12 }}>
              <div className="audit-block__title" style={{ marginBottom: 0 }}>
                Свод: {result.members.join(" + ") || "—"}
              </div>
              {a.n > 0 && (
                <Button
                  variant="ghost"
                  onClick={async () => {
                    try {
                      await downloadAuditXlsx(`${name || "Группа"}.xlsx`, a);
                      toast("Выгрузка XLSX скачана", { kind: "success" });
                    } catch {
                      toast("Не удалось сформировать выгрузку", { kind: "error" });
                    }
                  }}
                >
                  <IconDownload size={15} />
                  <span style={{ marginLeft: 6 }}>Выгрузка XLSX</span>
                </Button>
              )}
            </div>
            {a.n === 0 ? (
              <div className="page-sub" style={{ fontSize: 12.5 }}>
                Общих отчётных периодов нет — свод пуст. Приведите периоды участников к
                одинаковым подписям (например «2024»).
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table className="audit-grid">
                  <thead>
                    <tr>
                      <th className="audit-grid__rowhead">Статья</th>
                      {a.periods.map((p) => <th key={p}>{p}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {[...a.balance, ...a.income].map((ln) => (
                      <tr key={ln.code} className={ln.subtotal ? "audit-row--subtotal" : undefined}>
                        <td className="audit-grid__rowhead">{ln.label}</td>
                        {ln.values.map((v, t) => (
                          <td key={t} className="audit-val">{fmtNum(v, 0)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {a.n > 0 && (
            <>
              {RATIO_GROUPS.map(([key, title]) => {
                const group = a.ratios[key] ?? {};
                const names = Object.keys(group);
                if (names.length === 0) return null;
                return (
                  <div className="audit-block" key={key}>
                    <div className="audit-block__title">Коэффициенты группы — {title.toLowerCase()}</div>
                    <div style={{ overflowX: "auto" }}>
                      <table className="audit-grid">
                        <thead>
                          <tr>
                            <th className="audit-grid__rowhead">Показатель</th>
                            {a.periods.map((p) => <th key={p}>{p}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {names.map((nm) => (
                            <tr key={nm}>
                              <td className="audit-grid__rowhead">{nm}</td>
                              {group[nm].map((v, t) => (
                                <td key={t} className="audit-val">{fmtRatio(nm, v)}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}

              {a.diagnostics && (
                <div className={"diag-light diag-light--" + a.diagnostics.light}>
                  <div className="diag-light__title">Диагностика группы</div>
                  <div className="diag-light__sub">{a.diagnostics.summary}</div>
                </div>
              )}

              <div className="audit-block">
                <div className="audit-block__title">Заключение по группе</div>
                {a.opinion.split("\n\n").map((block, i) => (
                  <p key={i} className="opinion-block">{block}</p>
                ))}
              </div>
            </>
          )}
        </>
      )}

      {!result && (subjects ?? []).length > 0 && (
        <div className="tab-empty">
          <div className="tab-empty__ico"><IconBriefcase size={30} /></div>
          <div className="tab-empty__title">Свод не построен</div>
          <div className="tab-empty__sub">
            Отметьте участников группы и нажмите «Построить свод» — отчётность сложится по
            совпадающим периодам, а анализ посчитается для группы целиком.
          </div>
        </div>
      )}
    </div>
  );
}
