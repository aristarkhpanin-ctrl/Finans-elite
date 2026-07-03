import { useState } from "react";
import type { BreakEvenOut, RatioGroup, RatiosOut } from "../api/calc";
import { CountChip, SegmentControl } from "./ui";

const VIEW_KEY = "fe_ratios_view";
type View = "table" | "spark";

/** Группы коэффициентов: [ключ, название, цвет точки, описание]. */
const GROUPS: Array<[keyof RatiosOut, string, string, string]> = [
  ["liquidity", "Ликвидность", "var(--primary)", "Покрытие краткосрочных обязательств"],
  ["activity", "Деловая активность", "var(--info)", "Оборачиваемость активов и капитала"],
  ["gearing", "Структура капитала", "#5E93FF", "Долговая нагрузка и покрытие процентов"],
  ["profitability", "Рентабельность", "var(--warn)", "Маржинальность по уровням прибыли"],
  ["investment", "Инвестиционные (на акцию)", "#C77DFF", "Показатели в расчёте на акцию"],
];

type Unit = "×" | "%" | "дн." | "₽";

/** Юнит показателя по названию (Этап 14: чипы ×/%/дн./₽). */
function unitOf(name: string): Unit {
  if (name.includes("дн.")) return "дн.";
  if (
    name.startsWith("Рентабельность") ||
    name.includes("обязательства к активам") ||
    name.includes("Запас прочности")
  )
    return "%";
  if (
    name.includes("на акцию") ||
    name.includes("EPS") ||
    name.includes("оборотный капитал") ||
    name.includes("Дивиденды") ||
    name.includes("Порог выручки")
  )
    return "₽";
  return "×";
}

const NBSP = " ";

/** Значение с учётом юнита: % — доля×100, ₽ — с группировкой, прочее — 2 знака. */
function fmtVal(v: string | null, unit: Unit): string {
  if (v === null || v === undefined) return "—";
  const x = Number(v);
  if (!Number.isFinite(x)) return "—";
  if (unit === "%") return (x * 100).toFixed(1).replace(".", ",").replace("-", "−");
  if (unit === "₽") {
    const r = Math.round(x);
    return (r < 0 ? "−" : "") + String(Math.abs(r)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  }
  if (unit === "дн.") return x.toFixed(0).replace("-", "−");
  return x.toFixed(2).replace(".", ",").replace("-", "−");
}

function Sparkline({ values, color }: { values: (number | null)[]; color: string }) {
  const nums = values.filter((v): v is number => v !== null);
  if (nums.length < 2) return <div style={{ height: 30 }} />;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const range = max - min || 1;
  const w = 100;
  const h = 28;
  const pts = values
    .map((v, i) =>
      v === null ? null : `${(i / (values.length - 1)) * w},${h - 2 - ((v - min) / range) * (h - 4)}`,
    )
    .filter(Boolean)
    .join(" ");
  return (
    <svg width="100%" height={h + 2} viewBox={`0 0 ${w} ${h + 2}`} preserveAspectRatio="none" style={{ display: "block", marginTop: 8 }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function GroupSection({
  title,
  color,
  desc,
  group,
  n,
  view,
}: {
  title: string;
  color: string;
  desc: string;
  group: RatioGroup;
  n: number;
  view: View;
}) {
  const names = Object.keys(group);
  if (names.length === 0) return null;
  const months = Array.from({ length: n }, (_, i) => i);

  return (
    <div className="csec">
      <div className="csec__head">
        <div style={{ minWidth: 0 }}>
          <div className="csec__titlerow">
            <span className="csec__dot" style={{ background: color }} />
            <span className="csec__title">{title}</span>
            <CountChip>{names.length}</CountChip>
          </div>
          <div className="csec__desc">{desc}</div>
        </div>
      </div>

      {view === "table" ? (
        <div className="fin2-wrap fe-scroll">
          <div className="fin2">
            <div className="fin2-row">
              <div className="fin2-corner">Показатель</div>
              {months.map((i) => (
                <div key={i} className="fin2-month">
                  М{i + 1}
                </div>
              ))}
            </div>
            {names.map((name) => {
              const unit = unitOf(name);
              return (
                <div key={name} className="fin2-row">
                  <div className="fin2-label" title={name}>
                    <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {name}
                    </span>
                    <span className="ratio-unit">{unit}</span>
                  </div>
                  {months.map((i) => {
                    const v = group[name][i] ?? null;
                    const x = v === null ? null : Number(v);
                    return (
                      <div
                        key={i}
                        className={
                          "fin2-cell" + (x === null ? " fin2-cell--zero" : x < 0 ? " fin2-cell--neg" : "")
                        }
                      >
                        {fmtVal(v, unit)}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="spark-grid">
          {names.map((name) => {
            const unit = unitOf(name);
            const vals = months.map((i) => {
              const v = group[name][i];
              return v === null || v === undefined ? null : Number(v);
            });
            const nums = vals.filter((v): v is number => v !== null);
            const cur = nums.length ? nums[nums.length - 1] : null;
            const first = nums.length ? nums[0] : null;
            const delta = cur !== null && first !== null ? cur - first : null;
            return (
              <div key={name} className="spark-card">
                <div className="spark-card__top">
                  <span className="spark-card__name">{name}</span>
                  <span className="ratio-unit">{unit}</span>
                </div>
                <div className="spark-card__row">
                  <span className="spark-card__val">{cur !== null ? fmtVal(String(cur), unit) : "—"}</span>
                  {delta !== null && delta !== 0 && (
                    <span className={"spark-card__delta " + (delta > 0 ? "spark-card__delta--up" : "spark-card__delta--down")}>
                      {delta > 0 ? "↑" : "↓"} {fmtVal(String(Math.abs(delta)), unit)} к М1
                    </span>
                  )}
                </div>
                {nums.length > 0 && (
                  <div className="spark-card__minmax">
                    min {fmtVal(String(Math.min(...nums)), unit)} · max {fmtVal(String(Math.max(...nums)), unit)}
                  </div>
                )}
                <Sparkline values={vals} color={color} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Коэффициенты + безубыточность (макет «Этап 14», C1). */
export function RatiosView({
  ratios,
  breakEven,
  n,
}: {
  ratios: RatiosOut;
  breakEven?: BreakEvenOut;
  n: number;
}) {
  const [view, setView] = useState<View>(() => (localStorage.getItem(VIEW_KEY) as View) || "table");
  const setViewPersist = (v: View) => {
    setView(v);
    localStorage.setItem(VIEW_KEY, v);
  };

  const total =
    GROUPS.reduce((s, [key]) => s + Object.keys(ratios[key]).length, 0) + (breakEven ? 2 : 0);

  // C1: безубыточность как шестая группа
  const breakEvenGroup: RatioGroup | null = breakEven
    ? {
        "Порог выручки (точка безубыточности)": breakEven.break_even_revenue,
        "Запас прочности": breakEven.margin_of_safety,
      }
    : null;

  return (
    <div>
      <div className="report-head">
        <div style={{ minWidth: 0 }}>
          <div className="report-head__title">Коэффициенты и безубыточность</div>
          <div className="report-head__sub">{total} показателей · помесячная динамика</div>
        </div>
        <SegmentControl
          value={view}
          onChange={setViewPersist}
          options={[
            { value: "table", label: "Таблицы" },
            { value: "spark", label: "Спарклайны" },
          ]}
        />
      </div>

      {GROUPS.map(([key, title, color, desc]) => (
        <GroupSection key={key} title={title} color={color} desc={desc} group={ratios[key]} n={n} view={view} />
      ))}

      {breakEvenGroup && (
        <GroupSection
          title="Безубыточность"
          color="var(--good)"
          desc="Порог выручки и запас прочности по месяцам"
          group={breakEvenGroup}
          n={n}
          view={view}
        />
      )}
    </div>
  );
}
