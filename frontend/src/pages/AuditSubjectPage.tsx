import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ASSET_LINES,
  EQLIAB_LINES,
  INCOME_LINES,
  getAuditSubject,
  updateAuditSubject,
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

type Tab = "subject" | "input";

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
      setDirty(false);
      toast("Сохранено", { kind: "success" });
    },
    onError: () => toast("Не удалось сохранить", { kind: "error" }),
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

      <div className="seg" style={{ marginBottom: 16 }}>
        <button className={"seg__btn" + (tab === "subject" ? " seg__btn--active" : "")} onClick={() => setTab("subject")}>Субъект</button>
        <button className={"seg__btn" + (tab === "input" ? " seg__btn--active" : "")} onClick={() => setTab("input")}>Ввод отчётности</button>
      </div>

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
      ) : (
        <>
          {grid("balance", ASSET_LINES, "Баланс — актив")}
          {grid("balance", EQLIAB_LINES, "Баланс — пассив (капитал и обязательства)")}
          {grid("income", INCOME_LINES, "Отчёт о финансовых результатах")}
        </>
      )}
    </div>
  );
}
