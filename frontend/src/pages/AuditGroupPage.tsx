import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  RATIO_GROUPS,
  consolidateAudit,
  listAuditSubjects,
  type AuditConsolidation,
  type AuditElimination,
} from "../api/audit";
import { IconBriefcase } from "../components/icons";
import { useToast } from "../components/Toast";
import { Button } from "../components/ui";

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

/**
 * Консолидация группы предприятий (Финанс-Аудит, фаза H): выбор субъектов → свод →
 * анализ группы как единого предприятия. Внутригрупповые обороты вычитаются, только если
 * заданы явно; иначе выводится оговорка о завышении показателей группы.
 */
export function AuditGroupPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const { data: subjects, isLoading } = useQuery({
    queryKey: ["audit-subjects"],
    queryFn: listAuditSubjects,
  });

  const [selected, setSelected] = useState<string[]>([]);
  const [name, setName] = useState("Группа предприятий");
  const [result, setResult] = useState<AuditConsolidation | null>(null);
  // Внутригрупповые обороты к исключению (v2): по одному значению на период свода.
  const [elimOn, setElimOn] = useState(false);
  const [elimRec, setElimRec] = useState("");
  const [elimRev, setElimRev] = useState("");

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  /**
   * Одна сумма распространяется на все периоды свода (частый случай — одинаковый годовой
   * оборот). Ряд отправляется с запасом: сервер обрезает его до числа периодов свода.
   */
  const elimination = (): AuditElimination | undefined => {
    if (!elimOn) return undefined;
    const MAX_PERIODS = 48;   // верхняя граница числа периодов субъекта
    return {
      receivables: Array.from({ length: MAX_PERIODS }, () => elimRec || "0"),
      revenue: Array.from({ length: MAX_PERIODS }, () => elimRev || "0"),
    };
  };

  const run = useMutation({
    mutationFn: () => consolidateAudit(selected, name, elimination()),
    onSuccess: (r) => { setResult(r); toast("Свод построен", { kind: "success" }); },
    onError: () => toast("Не удалось построить свод", { kind: "error" }),
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
                     checked={elimOn} onChange={(e) => setElimOn(e.target.checked)} />
              <span className="opt-row__box">{elimOn ? "✓" : ""}</span>
              <span style={{ minWidth: 0 }}>
                <span className="opt-row__label">Исключить внутригрупповые обороты</span>
                <span className="opt-row__help">
                  Взаимная задолженность вычитается из дебиторки и кредиторки, взаимная выручка —
                  из выручки и себестоимости. Доли участия не исключаются.
                </span>
              </span>
            </label>
            {elimOn && (
              <div className="ft-row" style={{ marginBottom: 10 }}>
                <input className="efield__input" inputMode="decimal" value={elimRec}
                       placeholder="Взаимная задолженность за период"
                       onChange={(e) => setElimRec(e.target.value)} />
                <input className="efield__input" inputMode="decimal" value={elimRev}
                       placeholder="Взаимная выручка за период"
                       onChange={(e) => setElimRev(e.target.value)} />
              </div>
            )}
            <div className="ft-row">
              <input className="efield__input" value={name} placeholder="Название группы"
                     onChange={(e) => setName(e.target.value)} />
              <Button onClick={() => run.mutate()} loading={run.isPending}
                      disabled={selected.length === 0}>
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
            <div className="audit-block__title">
              Свод: {result.members.join(" + ") || "—"}
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
