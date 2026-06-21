import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { runMonteCarlo, SENSITIVITY_PARAMS, type UncertainParamIn } from "../../api/analysis";
import { money, percent } from "../../format";
import { Button } from "../../components/ui";

interface Row {
  param: string;
  kind: "uniform" | "normal";
  low: string;
  high: string;
  mean: string;
  std: string;
}

const newRow = (): Row => ({ param: "sales_price", kind: "uniform", low: "0.8", high: "1.2", mean: "1.0", std: "0.1" });

export function MonteCarloTab({ projectId }: { projectId: string }) {
  const [iterations, setIterations] = useState(500);
  const [seed, setSeed] = useState(42);
  const [rows, setRows] = useState<Row[]>([newRow()]);

  const toApi = (): UncertainParamIn[] =>
    rows.map((r) => ({
      param: r.param,
      distribution: r.kind === "uniform"
        ? { kind: "uniform", low: r.low, high: r.high }
        : { kind: "normal", mean: r.mean, std: r.std },
    }));

  const run = useMutation({ mutationFn: () => runMonteCarlo(projectId, { iterations, seed, uncertain: toApi() }) });

  const upd = (i: number, patch: Partial<Row>) => setRows(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const d = run.data;

  return (
    <div>
      <div className="form-grid" style={{ alignItems: "end" }}>
        <label className="field"><span>Итераций</span>
          <input className="input" type="number" value={iterations} min={1} max={2000}
                 onChange={(e) => setIterations(parseInt(e.target.value || "1", 10))} /></label>
        <label className="field"><span>Seed</span>
          <input className="input" type="number" value={seed} onChange={(e) => setSeed(parseInt(e.target.value || "0", 10))} /></label>
      </div>

      <div className="section-head"><h3 style={{ margin: 0 }}>Неопределённые параметры</h3>
        <Button variant="ghost" onClick={() => setRows([...rows, newRow()])}>+ Параметр</Button></div>
      {rows.map((r, i) => (
        <div className="row-card" key={i}>
          <div className="row-head">
            <select className="select" value={r.param} onChange={(e) => upd(i, { param: e.target.value })}>
              {SENSITIVITY_PARAMS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
            <select className="select" value={r.kind} onChange={(e) => upd(i, { kind: e.target.value as Row["kind"] })}>
              <option value="uniform">Равномерное</option>
              <option value="normal">Нормальное</option>
            </select>
            {r.kind === "uniform" ? (
              <>
                <input className="input" style={{ width: 90 }} value={r.low} title="мин" onChange={(e) => upd(i, { low: e.target.value })} />
                <input className="input" style={{ width: 90 }} value={r.high} title="макс" onChange={(e) => upd(i, { high: e.target.value })} />
              </>
            ) : (
              <>
                <input className="input" style={{ width: 90 }} value={r.mean} title="среднее" onChange={(e) => upd(i, { mean: e.target.value })} />
                <input className="input" style={{ width: 90 }} value={r.std} title="σ" onChange={(e) => upd(i, { std: e.target.value })} />
              </>
            )}
            <span className="grow" />
            <Button variant="ghost" onClick={() => setRows(rows.filter((_, k) => k !== i))}>×</Button>
          </div>
        </div>
      ))}

      <Button onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending ? "Расчёт…" : "Запустить"}</Button>
      {run.isError && <p className="error">Ошибка анализа</p>}

      {d && (
        <div className="metrics" style={{ marginTop: 16 }}>
          <div className="metric"><div className="m-label">P(NPV&gt;0)</div><div className="m-value">{percent(d.probability_npv_positive)}</div></div>
          <div className="metric"><div className="m-label">NPV среднее</div><div className="m-value">{money(d.npv_mean)}</div></div>
          <div className="metric"><div className="m-label">σ</div><div className="m-value">{money(d.npv_std)}</div></div>
          <div className="metric"><div className="m-label">P10</div><div className="m-value">{money(d.npv_p10)}</div></div>
          <div className="metric"><div className="m-label">Медиана</div><div className="m-value">{money(d.npv_p50)}</div></div>
          <div className="metric"><div className="m-label">P90</div><div className="m-value">{money(d.npv_p90)}</div></div>
        </div>
      )}
    </div>
  );
}
