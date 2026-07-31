import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ASSET_LINES,
  EQLIAB_LINES,
  INCOME_LINES,
  RATIO_GROUPS,
  analyzeAuditSubject,
  getAuditSubject,
  updateAuditSubject,
  type AuditLineOut,
  type AuditModel,
  type AuditPeriod,
} from "../api/audit";
import { IconTrash } from "../components/icons";
import { useToast } from "../components/Toast";
import { Button } from "../components/ui";
import { fmtMoney } from "../format";

const num = (v: string | undefined): number => {
  const x = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
};

/** Сумма значений строк группы по периоду t. */
function groupSum(table: Record<string, string[]>, codes: string[], t: number): number {
  return codes.reduce((s, c) => s + num(table[c]?.[t]), 0);
}

type Tab = "subject" | "input" | "reports" | "ratios" | "trends";

const TABS: [Tab, string][] = [
  ["subject", "Субъект"],
  ["input", "Ввод отчётности"],
  ["reports", "Отчёты"],
  ["ratios", "Коэффициенты"],
  ["trends", "Тренды"],
];

/** Число из строки-Decimal (для форматирования; пусто/невалидно → null). */
const dec = (v: string | null | undefined): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const x = Number(String(v).replace(",", "."));
  return Number.isFinite(x) ? x : null;
};

const fmtNum = (v: string | null | undefined, digits = 2): string => {
  const x = dec(v);
  return x === null ? "—" : x.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

const fmtPct = (v: string | null | undefined, digits = 1): string => {
  const x = dec(v);
  return x === null ? "—" : (x * 100).toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits }) + "%";
};

/** Показатели, которые выводятся как проценты (доли), а не как коэффициенты. */
const PCT_RATIOS = /^(Рентабельность|Коэффициент автономии|Суммарные обязательства)/;
/** Показатели в денежных единицах. */
const MONEY_RATIOS = /^(Чистый оборотный капитал)/;

export function AuditSubjectPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const { data, isLoading } = useQuery({
    queryKey: ["audit-subject", id],
    queryFn: () => getAuditSubject(id),
  });

  const [name, setName] = useState("");
  const [model, setModel] = useState<AuditModel | null>(null);
  const [tab, setTab] = useState<Tab>("subject");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (data) { setName(data.name); setModel(data.model); setDirty(false); }
  }, [data]);

  const save = useMutation({
    mutationFn: () => updateAuditSubject(id, name, model!),
    onSuccess: (s) => {
      qc.setQueryData(["audit-subject", id], s);
      qc.invalidateQueries({ queryKey: ["audit-subjects"] });
      qc.invalidateQueries({ queryKey: ["audit-analysis", id] });   // пересчитать анализ
      setDirty(false);
      toast("Сохранено", { kind: "success" });
    },
    onError: () => toast("Не удалось сохранить", { kind: "error" }),
  });

  // Анализ считается по сохранённым данным — только для аналитических вкладок.
  const isAnalysisTab = tab === "reports" || tab === "ratios" || tab === "trends";
  const analysis = useQuery({
    queryKey: ["audit-analysis", id],
    queryFn: () => analyzeAuditSubject(id),
    enabled: isAnalysisTab,
  });

  if (isLoading || !model) {
    return <div className="page-sub" style={{ padding: 24 }}>Загрузка…</div>;
  }
  const m = model;
  const n = m.periods.length;

  const patch = (p: Partial<AuditModel>) => { setModel({ ...m, ...p }); setDirty(true); };
  const setPeriod = (i: number, up: Partial<AuditPeriod>) =>
    patch({ periods: m.periods.map((p, k) => (k === i ? { ...p, ...up } : p)) });
  const addPeriod = () =>
    patch({ periods: [...m.periods, { label: "", kind: "year" }] });
  const removePeriod = (i: number) =>
    patch({ periods: m.periods.filter((_, k) => k !== i) });

  // Установить значение ячейки таблицы (balance|income) строки code в периоде t.
  const setCell = (which: "balance" | "income", code: string, t: number, v: string) => {
    const table = { ...m[which] };
    const row = [...(table[code] ?? [])];
    while (row.length < n) row.push("");
    row[t] = v;
    table[code] = row;
    patch({ [which]: table } as Partial<AuditModel>);
  };

  const assets = (t: number) => groupSum(m.balance, ASSET_LINES.map(([c]) => c), t);
  const eqliab = (t: number) => groupSum(m.balance, EQLIAB_LINES.map(([c]) => c), t);
  const gap = (t: number) => assets(t) - eqliab(t);
  const balanced = m.periods.every((_, t) => Math.abs(gap(t)) < 0.005);

  const grid = (which: "balance" | "income", lines: [string, string][], title: string) => (
    <div className="audit-block">
      <div className="audit-block__title">{title}</div>
      <div style={{ overflowX: "auto" }}>
        <table className="audit-grid">
          <thead>
            <tr>
              <th className="audit-grid__rowhead">Статья</th>
              {m.periods.map((p, t) => (
                <th key={t}>{p.label || `Период ${t + 1}`}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map(([code, label]) => (
              <tr key={code}>
                <td className="audit-grid__rowhead">{label}</td>
                {m.periods.map((_, t) => (
                  <td key={t}>
                    <input
                      className="audit-cell"
                      inputMode="decimal"
                      value={m[which][code]?.[t] ?? ""}
                      placeholder="0"
                      onChange={(e) => setCell(which, code, t, e.target.value)}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <button type="button" className="link-back" onClick={() => navigate("/audit")}>← К субъектам</button>
          <input
            className="subject-name"
            value={name}
            placeholder="Название субъекта"
            onChange={(e) => { setName(e.target.value); setDirty(true); }}
          />
        </div>
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!dirty}>
          Сохранить
        </Button>
      </div>

      <div className="seg" style={{ marginBottom: 16, flexWrap: "wrap" }}>
        {TABS.map(([key, label]) => (
          <button
            key={key}
            className={"seg__btn" + (tab === key ? " seg__btn--active" : "")}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {isAnalysisTab && dirty && (
        <div className="field-note field-note--warn" style={{ marginBottom: 12 }}>
          Есть несохранённые правки — анализ считается по сохранённым данным. Нажмите «Сохранить».
        </div>
      )}

      {/* Индикатор сходимости баланса (актив = пассив) */}
      <div className={"balance-banner " + (balanced ? "balance-banner--ok" : "balance-banner--bad")}>
        {balanced
          ? "Баланс сходится во всех периодах (актив = пассив)."
          : "Баланс не сходится — проверьте ввод:"}
        {!balanced && (
          <span className="balance-banner__gaps">
            {m.periods.map((p, t) => Math.abs(gap(t)) >= 0.005 && (
              <span key={t}>{p.label || `П${t + 1}`}: разрыв {fmtMoney(gap(t))}</span>
            ))}
          </span>
        )}
      </div>

      {tab === "subject" ? (
        <div className="audit-block">
          <div className="audit-block__title">Реквизиты и периоды</div>
          <div className="afields-grid" style={{ marginBottom: 16 }}>
            <label className="efield">
              <span className="efield__label">Валюта</span>
              <input className="efield__input" value={m.currency ?? ""} placeholder="RUB"
                     onChange={(e) => patch({ currency: e.target.value })} />
            </label>
            <label className="efield">
              <span className="efield__label">Отрасль</span>
              <input className="efield__input" value={m.industry ?? ""} placeholder="напр. Торговля"
                     onChange={(e) => patch({ industry: e.target.value })} />
            </label>
          </div>

          <div className="audit-block__title" style={{ fontSize: 13 }}>Отчётные периоды</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {m.periods.map((p, i) => (
              <div className="ft-row" key={i}>
                <input className="efield__input" value={p.label} placeholder={`Период ${i + 1} (напр. 2024)`}
                       onChange={(e) => setPeriod(i, { label: e.target.value })} />
                <select className="efield__input" value={p.kind}
                        onChange={(e) => setPeriod(i, { kind: e.target.value as AuditPeriod["kind"] })}>
                  <option value="year">Год</option>
                  <option value="quarter">Квартал</option>
                </select>
                <button type="button" className="line-card__del" title="Удалить период"
                        disabled={n <= 1} onClick={() => removePeriod(i)}>
                  <IconTrash size={15} />
                </button>
              </div>
            ))}
            <button type="button" className="add-row add-row--sm" onClick={addPeriod}>
              ＋&nbsp;&nbsp;Добавить период
            </button>
          </div>
        </div>
      ) : tab === "input" ? (
        <>
          {grid("balance", ASSET_LINES, "Баланс — актив")}
          {grid("balance", EQLIAB_LINES, "Баланс — пассив (капитал и обязательства)")}
          {grid("income", INCOME_LINES, "Отчёт о финансовых результатах")}
        </>
      ) : analysis.isLoading ? (
        <div className="page-sub" style={{ padding: 24 }}>Считаем анализ…</div>
      ) : analysis.isError || !analysis.data ? (
        <div className="error-state" style={{ padding: "40px 24px" }}>
          <div className="error-state__ico">!</div>
          <div className="error-state__title">Не удалось выполнить анализ</div>
          <Button variant="ghost" onClick={() => analysis.refetch()}>Повторить</Button>
        </div>
      ) : analysis.data.n === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">Нет периодов</div>
          <div className="tab-empty__sub">
            Добавьте отчётные периоды и введите отчётность — появятся отчёты, коэффициенты и тренды.
          </div>
        </div>
      ) : tab === "reports" ? (
        <>
          <StatementTable title="Баланс (аналитическая форма)"
                          periods={analysis.data.periods} lines={analysis.data.balance} />
          <StatementTable title="Отчёт о финансовых результатах"
                          periods={analysis.data.periods} lines={analysis.data.income} />
        </>
      ) : tab === "ratios" ? (
        <>
          {RATIO_GROUPS.map(([key, title]) => {
            const group = analysis.data.ratios[key] ?? {};
            const names = Object.keys(group);
            if (names.length === 0) return null;
            return (
              <div className="audit-block" key={key}>
                <div className="audit-block__title">{title}</div>
                <div style={{ overflowX: "auto" }}>
                  <table className="audit-grid">
                    <thead>
                      <tr>
                        <th className="audit-grid__rowhead">Показатель</th>
                        {analysis.data!.periods.map((p) => <th key={p}>{p}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {names.map((nm) => (
                        <tr key={nm}>
                          <td className="audit-grid__rowhead">{nm}</td>
                          {group[nm].map((v, t) => (
                            <td key={t} className="audit-val">
                              {MONEY_RATIOS.test(nm) ? fmtNum(v, 0)
                                : PCT_RATIOS.test(nm) ? fmtPct(v)
                                : fmtNum(v)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </>
      ) : (
        <>
          <div className="audit-block">
            <div className="audit-block__title">Горизонтальный анализ (изменение к предыдущему периоду)</div>
            <div style={{ overflowX: "auto" }}>
              <table className="audit-grid">
                <thead>
                  <tr>
                    <th className="audit-grid__rowhead">Статья</th>
                    {analysis.data.periods.map((p) => <th key={p} colSpan={2}>{p}</th>)}
                  </tr>
                  <tr>
                    <th className="audit-grid__rowhead"> </th>
                    {analysis.data.periods.map((p) => (
                      <React.Fragment key={p}>
                        <th style={{ fontWeight: 500 }}>Δ</th>
                        <th style={{ fontWeight: 500 }}>темп</th>
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {analysis.data.horizontal.map((t) => (
                    <tr key={t.code}>
                      <td className="audit-grid__rowhead">{t.label}</td>
                      {t.delta.map((d, i) => (
                        <React.Fragment key={i}>
                          <td className="audit-val">{d === null ? "—" : fmtNum(d, 0)}</td>
                          <td className={"audit-val " + trendTone(t.rate[i])}>{fmtPct(t.rate[i])}</td>
                        </React.Fragment>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="audit-block">
            <div className="audit-block__title">Вертикальный анализ (структура: доля в активе / выручке)</div>
            <div style={{ overflowX: "auto" }}>
              <table className="audit-grid">
                <thead>
                  <tr>
                    <th className="audit-grid__rowhead">Статья</th>
                    {analysis.data.periods.map((p) => <th key={p}>{p}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {analysis.data.vertical.map((s) => (
                    <tr key={s.code}>
                      <td className="audit-grid__rowhead">{s.label}</td>
                      {s.share.map((v, t) => <td key={t} className="audit-val">{fmtPct(v)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/** Знак темпа роста: рост — акцент, падение — тревожный тон. */
function trendTone(rate: string | null): string {
  const x = dec(rate);
  if (x === null || x === 0) return "";
  return x > 0 ? "audit-val--up" : "audit-val--down";
}

/** Таблица аналитической формы: строки-подытоги выделены. */
function StatementTable({ title, periods, lines }: {
  title: string;
  periods: string[];
  lines: AuditLineOut[];
}) {
  return (
    <div className="audit-block">
      <div className="audit-block__title">{title}</div>
      <div style={{ overflowX: "auto" }}>
        <table className="audit-grid">
          <thead>
            <tr>
              <th className="audit-grid__rowhead">Статья</th>
              {periods.map((p) => <th key={p}>{p}</th>)}
            </tr>
          </thead>
          <tbody>
            {lines.map((ln) => (
              <tr key={ln.code} className={ln.subtotal ? "audit-row--subtotal" : undefined}>
                <td className="audit-grid__rowhead">{ln.label}</td>
                {ln.values.map((v, t) => <td key={t} className="audit-val">{fmtNum(v, 0)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
