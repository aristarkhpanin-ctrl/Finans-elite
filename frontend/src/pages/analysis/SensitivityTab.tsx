import { useMutation } from "@tanstack/react-query";
import { httpDetail } from "../../api/client";
import { useState } from "react";
import { runSensitivity, SENSITIVITY_PARAMS, type SensitivityResponse } from "../../api/analysis";
import { CAT, MultiLineChart, type Series } from "../../components/charts";
import { ESelect } from "../../components/EditorField";
import { Button, ScrollRegion } from "../../components/ui";
import { fmtMillions, percent } from "../../format";

const DEFAULT_FACTORS = "0.8, 0.9, 1.0, 1.1, 1.2";

const num = (v: string): number => {
  const x = Number(String(v).replace(",", "."));
  return Number.isFinite(x) ? x : 0;
};
const fmtCoeff = (v: string) => Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 2 });

/** Вкладка «Чувствительность»: 5 параллельных прогонов, мультилиния, таблица. */
export function SensitivityTab({ projectId }: { projectId: string }) {
  const [param, setParam] = useState("sales_price");
  const [factorsText, setFactorsText] = useState(DEFAULT_FACTORS);
  const [editing, setEditing] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  const factors = factorsText.split(",").map((s) => s.trim()).filter(Boolean);

  // Пять параллельных запросов /sensitivity (по параметру на каждый) — все линии на графике.
  const run = useMutation({
    mutationFn: async () => {
      const results = await Promise.all(
        SENSITIVITY_PARAMS.map(([key]) => runSensitivity(projectId, key, factors)),
      );
      const map: Record<string, SensitivityResponse> = {};
      SENSITIVITY_PARAMS.forEach(([key], i) => (map[key] = results[i]));
      return map;
    },
  });

  const data = run.data;
  const labels = data ? data[SENSITIVITY_PARAMS[0][0]].points.map((p) => fmtCoeff(p.factor)) : [];

  const series: Series[] = data
    ? SENSITIVITY_PARAMS.map(([key, label], i) => ({
        key,
        label,
        color: CAT[i % CAT.length],
        values: data[key].points.map((p) => num(p.npv) / 1e6),
      })).filter((s) => !hidden.has(s.key))
    : [];

  // Таблица — по выбранному параметру, с Δ к базе (коэффициент 1) и профиль-баром.
  const selPoints = data?.[param].points ?? [];
  const basePoint = selPoints.find((p) => Math.abs(num(p.factor) - 1) < 1e-9);
  const baseNpv = basePoint ? num(basePoint.npv) : 0;
  const maxAbs = Math.max(1, ...selPoints.map((p) => Math.abs(num(p.npv))));

  const toggleLegend = (key: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div>
      <div className="an-head">
        <div style={{ minWidth: 0 }}>
          <h2 className="an-head__title">Анализ чувствительности</h2>
          <div className="an-head__sub">
            Как меняется NPV при отклонении одного параметра · остальные зафиксированы на базе.
          </div>
        </div>
      </div>

      <div className="cfg-card">
        <div className="cfg-field" style={{ flex: 1, minWidth: 220 }}>
          <ESelect label="Параметр" value={param} onChange={setParam} options={SENSITIVITY_PARAMS} />
        </div>
        <div className="cfg-field" style={{ flex: 1.3, minWidth: 240 }}>
          <label className="efield__label" htmlFor="sens-factors">Коэффициенты</label>
          {editing ? (
            <input
              id="sens-factors"
              className="input"
              style={{ height: 42, fontFamily: "var(--font-mono)" }}
              autoFocus
              value={factorsText}
              onChange={(e) => setFactorsText(e.target.value)}
              onBlur={() => setEditing(false)}
              onKeyDown={(e) => e.key === "Enter" && setEditing(false)}
            />
          ) : (
            <button
              type="button"
              id="sens-factors"
              className="coeff-box"
              onClick={() => setEditing(true)}
              title="Клик — редактировать множители"
              aria-label={`Коэффициенты ${factors.map(fmtCoeff).join(", ")} — изменить`}
            >
              {factors.map((f, i) => (
                <span key={i} className="coeff-chip">
                  {fmtCoeff(f)}
                </span>
              ))}
            </button>
          )}
        </div>
        <Button className="run-btn" loading={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? "Расчёт…" : "Рассчитать"}
        </Button>
      </div>

      {run.isIdle && (
        <div className="setup-ph">
          <div className="setup-ph__ico">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path d="M4 19V5M4 19h16M8 15l3-3 3 1 4-5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="setup-ph__title">Готово к расчёту</div>
          <div className="setup-ph__sub">
            Выберите параметр и коэффициенты, затем нажмите «Рассчитать» — построим кривую NPV и таблицу.
          </div>
        </div>
      )}

      {run.isPending && (
        <div className="load-card">
          <span className="save-spinner" />
          <div>
            <div className="load-card__title">Расчёт чувствительности…</div>
            <div className="load-card__sub">{SENSITIVITY_PARAMS.length} прогонов модели по коэффициентам</div>
          </div>
        </div>
      )}

      {run.isError && (
        <div className="an-err">
          <div className="an-err__ico">!</div>
          <div style={{ minWidth: 0 }}>
            <div className="an-err__title">Не удалось рассчитать</div>
            <div className="an-err__sub">
              {httpDetail(run.error) ??
                "Проверьте коэффициенты и параметры модели, затем повторите."}
            </div>
            <Button variant="ghost" onClick={() => run.mutate()}>
              Повторить расчёт
            </Button>
          </div>
        </div>
      )}

      {data && (
        <>
          <div className="chart-card2">
            <div className="chart-card2__title">NPV в зависимости от коэффициента</div>
            <div className="chart-card2__sub">Выделена выбранная переменная · ось Y — млн ₽</div>
            <div className="chart-legend" style={{ marginTop: 10 }}>
              {SENSITIVITY_PARAMS.map(([key, label], i) => (
                // Переключатель серии — кнопка с состоянием (K5): `span` со щелчком был
                // доступен только мыши, а скрытая серия отличалась лишь бледностью.
                <button
                  type="button"
                  key={key}
                  className={"leg-toggle" + (hidden.has(key) ? " leg-toggle--off" : "")}
                  aria-pressed={!hidden.has(key)}
                  onClick={() => toggleLegend(key)}
                >
                  <span className="leg-toggle__dot" style={{ background: CAT[i % CAT.length] }} />
                  {label}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 6 }}>
              <MultiLineChart label="Чувствительность NPV к параметрам, млн ₽" series={series}
                              labels={labels} selectedKey={hidden.has(param) ? undefined : param} />
            </div>
          </div>

          <ScrollRegion className="sens-table" label="Таблица чувствительности NPV">
            <div className="sens-row sens-row--head">
              <div className="sens-col-coeff">Коэффициент</div>
              <div className="sens-col-num">NPV, млн ₽</div>
              <div className="sens-col-num">Δ к базе</div>
              <div className="sens-col-num">IRR</div>
              <div className="sens-col-bar">профиль</div>
            </div>
            {selPoints.map((p, i) => {
              const npv = num(p.npv);
              const delta = npv - baseNpv;
              const isBase = Math.abs(num(p.factor) - 1) < 1e-9;
              return (
                <div className="sens-row" key={i}>
                  <div className="sens-col-coeff">
                    <span
                      className="dot-label"
                      style={{ background: npv < 0 ? "var(--danger)" : "var(--primary)" }}
                    />
                    {fmtCoeff(p.factor)}
                    {isBase && <span className="base-tag">база</span>}
                  </div>
                  <div className="sens-col-num" style={{ color: npv < 0 ? "var(--danger)" : "var(--text)" }}>
                    {fmtMillions(p.npv, { digits: 1 })}
                  </div>
                  <div
                    className="sens-col-num"
                    style={{ color: delta > 0 ? "var(--good)" : delta < 0 ? "var(--danger)" : "var(--subtle)" }}
                  >
                    {delta === 0 ? "—" : fmtMillions(String(delta), { sign: true, digits: 1 })}
                  </div>
                  <div className="sens-col-num" style={{ color: "var(--muted)" }}>
                    {p.irr_annual ? percent(p.irr_annual, 1) : "—"}
                  </div>
                  <div className="sens-col-bar">
                    <div className="profile-track">
                      <div
                        className="profile-fill"
                        style={{
                          width: `${(Math.abs(npv) / maxAbs) * 100}%`,
                          background: npv < 0 ? "var(--danger)" : "var(--primary)",
                        }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </ScrollRegion>
        </>
      )}
    </div>
  );
}
