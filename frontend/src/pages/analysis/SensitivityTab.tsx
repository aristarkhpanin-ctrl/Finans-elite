import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { runSensitivity, SENSITIVITY_PARAMS } from "../../api/analysis";
import { money } from "../../format";
import { SimpleLineChart } from "../../components/charts";
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

  const data = run.data?.points.map((p) => ({
    label: Number(p.factor).toLocaleString("ru-RU", { maximumFractionDigits: 2 }),
    value: Number(p.npv),
  }));

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
          <div className="chart-card2" style={{ marginTop: 14 }}>
            <div className="chart-card2__title">NPV в зависимости от параметра</div>
            <div className="chart-card2__sub">Множитель к базовому значению · NPV в ₽</div>
            <div style={{ marginTop: 10 }}>
              <SimpleLineChart points={data} valueLabel="NPV" />
            </div>
          </div>
          <div className="fin-table-wrap" style={{ marginTop: 14 }}>
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
