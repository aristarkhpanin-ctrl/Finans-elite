import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getJob, submitMonteCarloAsync, SENSITIVITY_PARAMS, type UncertainParamIn } from "../../api/analysis";
import { CAT, HistogramChart } from "../../components/charts";
import { CubeHero } from "../../components/CubeHero";
import { ESelect } from "../../components/EditorField";
import { Button } from "../../components/ui";
import { fmtMillions, percent } from "../../format";

type Kind = "uniform" | "normal" | "triangular";

interface Row {
  param: string;
  kind: Kind;
  low: string;
  high: string;
  mean: string;
  std: string;
  mode: string;
}

const newRow = (param = "sales_price"): Row => ({
  param,
  kind: "uniform",
  low: "0.8",
  high: "1.2",
  mean: "1.0",
  std: "0.1",
  mode: "1.0",
});

const DIST_OPTIONS: [string, string][] = [
  ["uniform", "Равномерное"],
  ["normal", "Нормальное"],
  ["triangular", "Треугольное"],
];

/** Поля распределения по типу (C4). */
const FIELDS: Record<Kind, Array<{ key: keyof Row; label: string }>> = {
  uniform: [
    { key: "low", label: "мин" },
    { key: "high", label: "макс" },
  ],
  normal: [
    { key: "mean", label: "среднее" },
    { key: "std", label: "σ" },
  ],
  triangular: [
    { key: "low", label: "мин" },
    { key: "mode", label: "мода" },
    { key: "high", label: "макс" },
  ],
};

export function MonteCarloTab({ projectId }: { projectId: string }) {
  const [iterations, setIterations] = useState(500);
  const [seed, setSeed] = useState(42);
  const [rows, setRows] = useState<Row[]>([newRow()]);

  const toApi = (): UncertainParamIn[] =>
    rows.map((r) => ({
      param: r.param,
      distribution:
        r.kind === "uniform"
          ? { kind: "uniform", low: r.low, high: r.high }
          : r.kind === "normal"
            ? { kind: "normal", mean: r.mean, std: r.std }
            : { kind: "triangular", low: r.low, mode: r.mode, high: r.high },
    }));

  // Асинхронный прогон: submit → фоновая задача → опрос статуса, пока не готово.
  const [jobId, setJobId] = useState<string | null>(null);
  const submit = useMutation({
    mutationFn: () => submitMonteCarloAsync(projectId, { iterations, seed, uncertain: toApi() }),
    onSuccess: (r) => setJobId(r.job_id),
  });
  const job = useQuery({
    queryKey: ["mc-job", jobId],
    queryFn: () => getJob(jobId as string),
    enabled: jobId != null,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "success" || s === "failure" ? false : 900;
    },
  });

  const upd = (i: number, patch: Partial<Row>) => setRows(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const d = job.data?.status === "success" ? job.data.result : undefined;
  const failed = job.data?.status === "failure";
  const running = submit.isPending || (jobId != null && !d && !failed);
  const idle = jobId == null && !submit.isPending;
  const errored = submit.isError || failed;
  const start = () => submit.mutate();

  const stats = d
    ? [
        { label: "Среднее NPV", value: fmtMillions(d.npv_mean, { digits: 1 }) },
        { label: "Ст. ошибка среднего", value: "±" + fmtMillions(d.npv_sem, { digits: 2 }) },
        { label: "σ (разброс)", value: fmtMillions(d.npv_std, { digits: 1 }) },
        { label: "P(NPV > 0)", value: percent(d.probability_npv_positive, 0), accent: true },
        { label: "VaR 95% (P5)", value: fmtMillions(d.npv_p5, { digits: 1 }) },
        { label: "CVaR 95% (худшие 5%)", value: fmtMillions(d.npv_cvar_5, { digits: 1 }) },
        { label: "Минимум", value: fmtMillions(d.npv_min, { digits: 1 }) },
        { label: "P10", value: fmtMillions(d.npv_p10, { digits: 1 }) },
        { label: "P50 (медиана)", value: fmtMillions(d.npv_p50, { digits: 1 }) },
        { label: "P90", value: fmtMillions(d.npv_p90, { digits: 1 }) },
        { label: "P95", value: fmtMillions(d.npv_p95, { digits: 1 }) },
        { label: "Максимум", value: fmtMillions(d.npv_max, { digits: 1 }) },
      ]
    : [];

  return (
    <div>
      <div className="an-head">
        <div style={{ minWidth: 0 }}>
          <div className="an-head__title">Монте-Карло</div>
          <div className="an-head__sub">
            Случайные прогоны при заданных распределениях параметров → распределение NPV.
          </div>
        </div>
      </div>

      <div className="cfg-card">
        <div className="cfg-field" style={{ width: 150 }}>
          <label className="efield__label">Итераций</label>
          <input
            className="input"
            style={{ height: 42, fontFamily: "var(--font-mono)" }}
            inputMode="numeric"
            value={iterations}
            onChange={(e) => setIterations(Math.max(1, Math.min(2000, parseInt(e.target.value || "1", 10) || 1)))}
          />
        </div>
        <div className="cfg-field" style={{ width: 130 }}>
          <label className="efield__label">Seed</label>
          <input
            className="input"
            style={{ height: 42, fontFamily: "var(--font-mono)" }}
            inputMode="numeric"
            value={seed}
            onChange={(e) => setSeed(parseInt(e.target.value || "0", 10) || 0)}
          />
        </div>
        <div style={{ flex: 1 }} />
        <Button className="run-btn" loading={running} onClick={start}>
          {running ? "Симуляция…" : "Запустить"}
        </Button>
      </div>

      <div className="terms-head" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span>Неопределённые параметры</span>
        <Button variant="ghost" onClick={() => setRows([...rows, newRow()])}>
          ＋&nbsp;&nbsp;Параметр
        </Button>
      </div>
      <div className="mc-tbl fe-scroll">
        <div className="mc-row mc-row--head">
          <div className="mc-col-param">Параметр</div>
          <div className="mc-col-dist">Распределение</div>
          <div className="mc-col-fields">Параметры распределения</div>
        </div>
        {rows.map((r, i) => (
          <div className="mc-row" key={i}>
            <div className="mc-col-param">
              <span className="dot-label" style={{ background: CAT[i % CAT.length] }} />
              <ESelect label="" value={r.param} onChange={(v) => upd(i, { param: v })} options={SENSITIVITY_PARAMS} />
            </div>
            <div className="mc-col-dist">
              <ESelect label="" value={r.kind} onChange={(v) => upd(i, { kind: v as Kind })} options={DIST_OPTIONS} />
            </div>
            <div className="mc-col-fields">
              {FIELDS[r.kind].map((fl) => (
                <div className="mc-field" key={fl.key}>
                  <span className="mc-field__label">{fl.label}</span>
                  <input
                    inputMode="decimal"
                    value={r[fl.key]}
                    onChange={(e) => upd(i, { [fl.key]: e.target.value } as Partial<Row>)}
                  />
                </div>
              ))}
              <button
                type="button"
                className="scn-del"
                style={{ alignSelf: "flex-end" }}
                title="Удалить параметр"
                onClick={() => setRows(rows.filter((_, k) => k !== i))}
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>

      {idle && (
        <div className="setup-ph">
          <div className="setup-ph__ico">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M3 3v18h18M7 14l3-4 3 3 5-7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="setup-ph__title">Запустите симуляцию</div>
          <div className="setup-ph__sub">
            {iterations} прогонов модели со случайными значениями параметров — получим распределение
            NPV и вероятность NPV&nbsp;&gt;&nbsp;0.
          </div>
        </div>
      )}

      {running && (
        <div className="mc-prog">
          <div className="mc-prog__top">
            <div className="mc-prog__cube">
              <CubeHero backdrop="transparent" showEnvironment={false} motionSpeed="energetic" pointerTilt={false} />
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="load-card__title">Симуляция Монте-Карло…</div>
              <div className="load-card__sub">{iterations} прогонов в фоне · оценка распределения NPV</div>
            </div>
          </div>
          <div className="mc-prog__track">
            <div className="mc-prog__bar" />
          </div>
        </div>
      )}

      {errored && (
        <div className="an-err">
          <div className="an-err__ico">!</div>
          <div style={{ minWidth: 0 }}>
            <div className="an-err__title">Не удалось выполнить симуляцию</div>
            <div className="an-err__sub">
              {(failed && job.data?.error) || "Проверьте распределения параметров и повторите."}
            </div>
            <Button variant="ghost" onClick={start}>
              Повторить
            </Button>
          </div>
        </div>
      )}

      {d && (
        <>
          <div className="stat-grid">
            {stats.map((s) => (
              <div key={s.label} className={"stat-card" + (s.accent ? " stat-card--accent" : "")}>
                <div className="stat-card__label">{s.label}</div>
                <div className="stat-card__value">{s.value}</div>
              </div>
            ))}
          </div>
          <p className="muted" style={{ margin: "10px 2px 0", fontSize: 12.5, lineHeight: 1.5 }}>
            <b>VaR 95%</b> — в 95% исходов NPV не хуже этого значения (5-й перцентиль).{" "}
            <b>CVaR 95%</b> — среднее по худшим 5% исходов (насколько плохо в «хвосте»).{" "}
            <b>± ст. ошибка</b> — точность оценки среднего (σ/√N): уже её — увеличьте число итераций.
          </p>

          <div className="chart-card2">
            <div className="chart-card2__title">Распределение NPV</div>
            <div className="chart-card2__sub">
              {d.iterations} итераций · ось X — млн ₽ · красная линия — порог NPV = 0
            </div>
            <div className="chart-legend" style={{ marginTop: 10 }}>
              <span className="chart-legend__item">
                <span style={{ width: 9, height: 9, borderRadius: 3, background: "var(--primary)", flex: "none" }} />
                NPV &gt; 0
              </span>
              <span className="chart-legend__item">
                <span style={{ width: 9, height: 9, borderRadius: 3, background: "var(--danger)", flex: "none" }} />
                NPV &lt; 0
              </span>
            </div>
            <div style={{ marginTop: 6 }}>
              <HistogramChart
                bins={d.histogram.map((b) => ({ from: Number(b.from) / 1e6, to: Number(b.to) / 1e6, count: b.count }))}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
