import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { runSensitivity, SENSITIVITY_PARAMS } from "../../api/analysis";
import { money } from "../../format";
import { Button } from "../../components/ui";

export function SensitivityTab({ projectId }: { projectId: string }) {
  const [param, setParam] = useState("sales_price");
  const [factorsText, setFactorsText] = useState("0.8, 0.9, 1.0, 1.1, 1.2");

  const run = useMutation({
    mutationFn: () => {
      const factors = factorsText.split(",").map((s) => s.trim()).filter(Boolean);
      return runSensitivity(projectId, param, factors);
    },
  });

  const data = run.data?.points.map((p) => ({ factor: Number(p.factor), npv: Number(p.npv) }));

  return (
    <div>
      <div className="form-grid" style={{ alignItems: "end" }}>
        <label className="field">
          <span>Параметр</span>
          <select className="select" value={param} onChange={(e) => setParam(e.target.value)}>
            {SENSITIVITY_PARAMS.map(([k, label]) => (
              <option key={k} value={k}>{label}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Коэффициенты (через запятую)</span>
          <input className="input" value={factorsText} onChange={(e) => setFactorsText(e.target.value)} />
        </label>
        <Button onClick={() => run.mutate()} disabled={run.isPending}>Рассчитать</Button>
      </div>

      {run.isError && <p className="error">Ошибка анализа</p>}
      {data && (
        <>
          <div className="chart-card" style={{ marginTop: 14 }}>
            <h3>NPV в зависимости от параметра</h3>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={data} margin={{ top: 6, right: 12, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="factor" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(v) => Number(v).toLocaleString("ru-RU", { notation: "compact" })}
                       tick={{ fontSize: 12 }} width={64} />
                <Tooltip formatter={(v: number) => money(String(v))} />
                <Line dataKey="npv" name="NPV" stroke="#2563eb" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="fin-table-wrap">
            <table className="fin-table">
              <thead><tr><th className="label-col">Коэффициент</th><th className="num">NPV</th></tr></thead>
              <tbody>
                {run.data!.points.map((p) => (
                  <tr key={p.factor}>
                    <td className="label-col">{p.factor}</td>
                    <td className="num">{money(p.npv)}</td>
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
