import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { runWhatIf, SENSITIVITY_PARAMS, type ScenarioIn } from "../../api/analysis";
import { money, percent } from "../../format";
import { Button } from "../../components/ui";

const newScenario = (n: number): ScenarioIn => ({
  name: `Сценарий ${n}`,
  adjustments: [{ param: "sales_price", factor: "1.1" }],
});

export function WhatIfTab({ projectId }: { projectId: string }) {
  const [scenarios, setScenarios] = useState<ScenarioIn[]>([newScenario(1)]);
  const run = useMutation({ mutationFn: () => runWhatIf(projectId, scenarios) });

  const updScenario = (i: number, patch: Partial<ScenarioIn>) =>
    setScenarios(scenarios.map((s, k) => (k === i ? { ...s, ...patch } : s)));
  const updAdj = (si: number, ai: number, patch: Partial<{ param: string; factor: string }>) =>
    updScenario(si, {
      adjustments: scenarios[si].adjustments.map((a, k) => (k === ai ? { ...a, ...patch } : a)),
    });

  const chartData = run.data?.scenarios.map((s) => ({ name: s.name, npv: Number(s.npv) }));

  return (
    <div>
      <div className="section-head"><h3 style={{ margin: 0 }}>Сценарии</h3>
        <Button variant="ghost" onClick={() => setScenarios([...scenarios, newScenario(scenarios.length + 1)])}>+ Сценарий</Button></div>

      {scenarios.map((s, si) => (
        <div className="row-card" key={si}>
          <div className="row-head">
            <input className="input grow" value={s.name} onChange={(e) => updScenario(si, { name: e.target.value })} />
            <Button variant="ghost" onClick={() => updScenario(si, { adjustments: [...s.adjustments, { param: "direct_costs", factor: "0.9" }] })}>+ Корректировка</Button>
            <Button variant="ghost" onClick={() => setScenarios(scenarios.filter((_, k) => k !== si))}>Удалить</Button>
          </div>
          {s.adjustments.map((a, ai) => (
            <div className="row-head" key={ai}>
              <select className="select" value={a.param} onChange={(e) => updAdj(si, ai, { param: e.target.value })}>
                {SENSITIVITY_PARAMS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
              <input className="input" style={{ width: 110 }} value={a.factor} title="коэффициент"
                     onChange={(e) => updAdj(si, ai, { factor: e.target.value })} />
              <span className="grow" />
              <Button variant="ghost" onClick={() => updScenario(si, { adjustments: s.adjustments.filter((_, k) => k !== ai) })}>×</Button>
            </div>
          ))}
        </div>
      ))}

      <Button onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending ? "Расчёт…" : "Сравнить"}</Button>
      {run.isError && <p className="error">Ошибка анализа</p>}

      {run.data && (
        <>
          <div className="chart-card" style={{ marginTop: 16 }}>
            <h3>NPV по сценариям</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={chartData} margin={{ top: 6, right: 12, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(v) => Number(v).toLocaleString("ru-RU", { notation: "compact" })} tick={{ fontSize: 12 }} width={64} />
                <Tooltip formatter={(v: number) => money(String(v))} />
                <Bar dataKey="npv" name="NPV" fill="#2563eb" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="fin-table-wrap">
            <table className="fin-table">
              <thead><tr>
                <th className="label-col">Сценарий</th><th className="num">NPV</th><th className="num">IRR</th>
                <th className="num">PI</th><th className="num">Окупаемость</th>
              </tr></thead>
              <tbody>
                {run.data.scenarios.map((s, i) => (
                  <tr key={i}>
                    <td className="label-col">{s.name}</td>
                    <td className="num">{money(s.npv)}</td>
                    <td className="num">{s.irr_annual ? percent(s.irr_annual) : "—"}</td>
                    <td className="num">{s.pi ? Number(s.pi).toFixed(2) : "—"}</td>
                    <td className="num">{s.pb_months ?? "—"} мес.</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
