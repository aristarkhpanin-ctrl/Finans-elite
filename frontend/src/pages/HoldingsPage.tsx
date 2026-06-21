import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { CalcResponse } from "../api/calc";
import {
  addHoldingMember,
  consolidateHolding,
  createHolding,
  deleteHolding,
  type Holding,
  HOLDING_ROLES,
  listHoldings,
} from "../api/holdings";
import { listProjects } from "../api/projects";
import type { ProjectSummary } from "../api/types";
import { RatiosView } from "../components/RatiosView";
import { StatementTable, SUBTOTALS } from "../components/StatementTable";
import { Button, Card } from "../components/ui";
import { money, percent } from "../format";

const holdingRole = (role: string) => HOLDING_ROLES.find(([k]) => k === role)?.[1] ?? role;

export function HoldingsPage() {
  const qc = useQueryClient();
  const holdings = useQuery({ queryKey: ["holdings"], queryFn: listHoldings });
  const projects = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => createHolding(name.trim()),
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["holdings"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteHolding(id),
    onSuccess: () => {
      setSelected(null);
      qc.invalidateQueries({ queryKey: ["holdings"] });
    },
  });

  const list = holdings.data ?? [];
  const current = list.find((h) => h.id === selected) ?? null;

  return (
    <div>
      <h1>Холдинги</h1>
      <p className="muted">Группа проектов и сводный бюджет (консолидация отчётов).</p>

      <Card style={{ marginBottom: 16 }}>
        <div className="toolbar">
          <input className="input grow" placeholder="Название холдинга" value={name}
                 onChange={(e) => setName(e.target.value)} />
          <Button disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>+ Создать</Button>
        </div>
        {create.isError && <p className="error">Не удалось создать (нужны права / квота).</p>}
      </Card>

      {list.length === 0 && <p className="muted">Холдингов пока нет.</p>}
      <div className="list" style={{ marginBottom: 16 }}>
        {list.map((h) => (
          <div className="list-item" key={h.id}>
            <div>
              <strong>{h.name}</strong> <span className="muted">· проектов: {h.members.length}</span>
            </div>
            <div className="actions">
              <Button variant="ghost" onClick={() => setSelected(h.id === selected ? null : h.id)}>
                {h.id === selected ? "Скрыть" : "Открыть"}
              </Button>
              <Button variant="ghost" onClick={() => remove.mutate(h.id)}>Удалить</Button>
            </div>
          </div>
        ))}
      </div>

      {current && <HoldingDetail holding={current} projects={projects.data ?? []} />}
    </div>
  );
}

function HoldingDetail({ holding, projects }: { holding: Holding; projects: ProjectSummary[] }) {
  const qc = useQueryClient();
  const [projectId, setProjectId] = useState("");
  const [role, setRole] = useState("subsidiary");
  const [result, setResult] = useState<CalcResponse | null>(null);

  const projectName = (id: string) => projects.find((p) => p.id === id)?.name ?? id;
  const memberIds = new Set(holding.members.map((m) => m.project_id));
  const available = projects.filter((p) => !memberIds.has(p.id));
  const pick = projectId || available[0]?.id || "";

  const add = useMutation({
    mutationFn: () => addHoldingMember(holding.id, pick, role),
    onSuccess: () => {
      setProjectId("");
      setResult(null);
      qc.invalidateQueries({ queryKey: ["holdings"] });
    },
  });
  const consolidate = useMutation({
    mutationFn: () => consolidateHolding(holding.id),
    onSuccess: (data) => setResult(data),
  });

  return (
    <Card>
      <h2>{holding.name}</h2>
      <h3 style={{ margin: "10px 0 8px" }}>Участники</h3>
      {holding.members.length === 0 && <p className="muted">Добавьте проекты в холдинг.</p>}
      <div className="list">
        {holding.members.map((m) => (
          <div className="list-item" key={m.project_id}>
            <span>{projectName(m.project_id)}</span>
            <span className="muted">{holdingRole(m.role)}</span>
          </div>
        ))}
      </div>

      {available.length > 0 && (
        <div className="toolbar" style={{ marginTop: 12 }}>
          <select className="select" value={pick} onChange={(e) => setProjectId(e.target.value)}>
            {available.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <select className="select" value={role} onChange={(e) => setRole(e.target.value)}>
            {HOLDING_ROLES.map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
          <Button onClick={() => add.mutate()} disabled={add.isPending}>Добавить проект</Button>
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <Button onClick={() => consolidate.mutate()}
                disabled={holding.members.length === 0 || consolidate.isPending}>
          {consolidate.isPending ? "Консолидация…" : "Консолидировать →"}
        </Button>
        {consolidate.isError && (
          <span className="error" style={{ marginLeft: 10 }}>
            {(consolidate.error as any)?.response?.data?.detail ?? "Ошибка консолидации"}
          </span>
        )}
      </div>

      {result && <ConsolidatedResults result={result} />}
    </Card>
  );
}

const RESULT_TABS = [
  ["income", "ОПУ"],
  ["cashflow", "Кэш-фло"],
  ["balance", "Баланс"],
  ["ratios", "Коэффициенты"],
] as const;

function ConsolidatedResults({ result }: { result: CalcResponse }) {
  const [tab, setTab] = useState<string>("income");
  const m = result.metrics;
  return (
    <div style={{ marginTop: 18 }}>
      <h3>Сводный бюджет <span className="muted">· движок {result.engine_version}</span></h3>
      {result.warnings.length > 0 && <div className="warnings">{result.warnings.join("; ")}</div>}
      <div className="metrics">
        <div className="metric"><div className="m-label">NPV</div><div className="m-value">{money(m.npv)}</div></div>
        <div className="metric"><div className="m-label">IRR</div><div className="m-value">{m.irr_annual ? percent(m.irr_annual) : "—"}</div></div>
        <div className="metric"><div className="m-label">PI</div><div className="m-value">{m.pi ? Number(m.pi).toFixed(2) : "—"}</div></div>
      </div>
      <div className="tabs">
        {RESULT_TABS.map(([key, label]) => (
          <button key={key} className={`tab ${tab === key ? "tab--active" : ""}`} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "income" && <StatementTable statement={result.income} n={result.n} subtotals={SUBTOTALS.income} />}
      {tab === "cashflow" && <StatementTable statement={result.cashflow} n={result.n} subtotals={SUBTOTALS.cashflow} />}
      {tab === "balance" && <StatementTable statement={result.balance} n={result.n} subtotals={SUBTOTALS.balance} />}
      {tab === "ratios" && <RatiosView ratios={result.ratios} n={result.n} />}
    </div>
  );
}
