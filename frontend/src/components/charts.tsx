import { useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import { fmtAxis, fmtMoney } from "../format";

/**
 * Общие SVG-примитивы графиков (порт «Этапа 15»): рамка, слой осей,
 * пустое состояние, палитра — плюс простые линейный и столбчатый
 * графики для вкладок анализа.
 */

export interface P {
  w: number;
  h: number;
  mL: number;
  mR: number;
  mT: number;
  mB: number;
}

export interface Frame {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
  iw: number;
  ih: number;
}

export const frame = (p: P): Frame => ({
  x0: p.mL,
  x1: p.w - p.mR,
  y0: p.h - p.mB,
  y1: p.mT,
  iw: p.w - p.mL - p.mR,
  ih: p.h - p.mT - p.mB,
});

/** Категориальная палитра (--chart-1..7, живёт при смене темы). */
export const CAT = [1, 2, 3, 4, 5, 6, 7].map((i) => `var(--chart-${i})`);
export const PAL = { op: CAT[0], inv: CAT[2], cash: CAT[3], pos: "var(--primary)", neg: "var(--danger)" };

export const AXIS_FONT = "600 10px 'JetBrains Mono', monospace";
export const XLBL_FONT = "600 9.5px 'JetBrains Mono', monospace";

export function monthLabels(n: number): (string | null)[] {
  return Array.from({ length: n }, (_, i) => (n <= 12 || i % 3 === 0 || i === n - 1 ? `М${i + 1}` : null));
}

/** Сетка + подписи оси Y (4 деления) и подписи X. */
export function axisLayer(
  f: Frame,
  min: number,
  max: number,
  labels: (string | null)[] | null,
  zeroEmph: boolean,
): ReactNode[] {
  const kids: ReactNode[] = [];
  const ticks = 4;
  for (let k = 0; k <= ticks; k++) {
    const v = min + ((max - min) * k) / ticks;
    const y = f.y0 - ((v - min) / (max - min || 1)) * f.ih;
    const zero = Math.abs(v) < 1e-6;
    kids.push(
      <line
        key={`g${k}`}
        x1={f.x0}
        y1={y}
        x2={f.x1}
        y2={y}
        stroke={zero && zeroEmph ? "var(--border-strong)" : "var(--grid-line)"}
        strokeWidth={zero && zeroEmph ? 1.4 : 1}
      />,
      <text key={`gl${k}`} x={f.x0 - 8} y={y + 3.5} textAnchor="end" style={{ font: AXIS_FONT, fill: "var(--subtle)" }}>
        {fmtAxis(v)}
      </text>,
    );
  }
  if (labels) {
    const n = labels.length;
    labels.forEach((lb, i) => {
      if (lb == null) return;
      kids.push(
        <text
          key={`x${i}`}
          x={f.x0 + ((i + 0.5) / n) * f.iw}
          y={f.y0 + 16}
          textAnchor="middle"
          style={{ font: XLBL_FONT, fill: "var(--subtle)" }}
        >
          {lb}
        </text>,
      );
    });
  }
  return kids;
}

export const Svg = ({ p, children }: { p: P; children: ReactNode }) => (
  <svg width="100%" height="100%" viewBox={`0 0 ${p.w} ${p.h}`} preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
    {children}
  </svg>
);

export function EmptyChart({ p }: { p: P }) {
  const f = frame(p);
  return (
    <Svg p={p}>
      <rect x={f.x0} y={f.y1} width={f.iw} height={f.ih} fill="none" stroke="var(--grid-line)" strokeWidth={1} strokeDasharray="4 5" rx={8} />
      <text x={p.w / 2} y={p.h / 2 - 2} textAnchor="middle" style={{ font: "600 13px Inter, sans-serif", fill: "var(--subtle)" }}>
        Нет данных для графика
      </text>
      <text x={p.w / 2} y={p.h / 2 + 16} textAnchor="middle" style={{ font: "500 10px Inter, sans-serif", fill: "var(--subtle)" }}>
        Запустите расчёт, чтобы построить визуализацию
      </text>
    </Svg>
  );
}

export interface TipRow {
  label: string;
  val: string;
  dot: string;
}

interface LocalTip {
  x: number;
  y: number;
  hostW: number;
  title: string;
  rows: TipRow[];
}

/** Обёртка карточки с локальным hover-тултипом. */
function useLocalTip() {
  const [tip, setTip] = useState<LocalTip | null>(null);
  const mkTip = (title: string, rows: TipRow[]) => (e: MouseEvent<SVGElement>) => {
    const host = (e.currentTarget as unknown as Element).closest("[data-chart-host]");
    if (!host) return;
    const r = host.getBoundingClientRect();
    setTip({ x: e.clientX - r.left, y: e.clientY - r.top, hostW: r.width, title, rows });
  };
  return { tip, mkTip, clearTip: () => setTip(null) };
}

function TipCard({ tip }: { tip: LocalTip }) {
  return (
    <div
      className="chart-tip"
      style={{
        left: tip.x + 14 + 190 > tip.hostW ? Math.max(8, tip.x - 196) : tip.x + 14,
        top: Math.max(8, tip.y - 10),
      }}
    >
      <div className="chart-tip__title">{tip.title}</div>
      {tip.rows.map((r, k) => (
        <div key={k} className="chart-tip__row">
          <span className="chart-tip__dot" style={{ background: r.dot }} />
          <span className="chart-tip__label">{r.label}</span>
          <span className="chart-tip__val">{r.val}</span>
        </div>
      ))}
    </div>
  );
}

/** Простой линейный график (значение по точкам-меткам) с ховером. */
export function SimpleLineChart({
  points,
  height = 260,
  valueLabel = "Значение",
}: {
  points: Array<{ label: string; value: number }>;
  height?: number;
  valueLabel?: string;
}) {
  const { tip, mkTip, clearTip } = useLocalTip();
  const p: P = { w: 900, h: 240, mL: 52, mR: 16, mT: 16, mB: 26 };
  const f = frame(p);
  const n = points.length;
  if (n === 0) return <EmptyChart p={p} />;
  const vals = points.map((d) => d.value);
  let min = Math.min(0, ...vals);
  let max = Math.max(0, ...vals);
  const pd = (max - min || 1) * 0.1;
  min -= pd;
  max += pd;
  const Y = (v: number) => f.y0 - ((v - min) / (max - min || 1)) * f.ih;
  const band = f.iw / n;
  const cx = (i: number) => f.x0 + (i + 0.5) * band;
  const kids: ReactNode[] = axisLayer(f, min, max, points.map((d) => d.label), true);
  const lp = vals.map((v, i) => `${cx(i).toFixed(1)},${Y(v).toFixed(1)}`);
  kids.push(
    <polyline key="ln" points={lp.join(" ")} fill="none" stroke={PAL.pos} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />,
  );
  vals.forEach((v, i) =>
    kids.push(<circle key={`c${i}`} cx={cx(i)} cy={Y(v)} r={3} fill={PAL.pos} stroke="var(--surface)" strokeWidth={1.2} />),
  );
  for (let i = 0; i < n; i++)
    kids.push(
      <rect
        key={`hb${i}`}
        x={f.x0 + (i / n) * f.iw}
        y={f.y1}
        width={f.iw / n}
        height={f.ih}
        fill="transparent"
        style={{ cursor: "crosshair" }}
        onMouseEnter={mkTip(points[i].label, [{ label: valueLabel, val: fmtMoney(vals[i]), dot: PAL.pos }])}
        onMouseMove={mkTip(points[i].label, [{ label: valueLabel, val: fmtMoney(vals[i]), dot: PAL.pos }])}
        onMouseLeave={clearTip}
      />,
    );
  return (
    <div data-chart-host style={{ position: "relative", height }}>
      <Svg p={p}>{kids}</Svg>
      {tip && <TipCard tip={tip} />}
    </div>
  );
}

export interface Series {
  key: string;
  label: string;
  color: string;
  values: number[];
}

/**
 * Мультилинейный график (чувствительность): несколько серий на общей оси X;
 * выбранная — жирнее и ярче, остальные приглушены; вертикаль «база» у x=1.
 * Легенда-toggle реализуется снаружи (передаётся отфильтрованный список серий).
 */
export function MultiLineChart({
  series,
  labels,
  selectedKey,
  height = 280,
  yUnit = "млн ₽",
}: {
  series: Series[];
  labels: string[];
  selectedKey?: string;
  height?: number;
  yUnit?: string;
}) {
  const { tip, mkTip, clearTip } = useLocalTip();
  const p: P = { w: 900, h: 260, mL: 48, mR: 16, mT: 22, mB: 28 };
  const f = frame(p);
  const nx = labels.length;
  if (series.length === 0 || nx === 0) return <EmptyChart p={p} />;
  const all = series.flatMap((s) => s.values);
  let min = Math.min(0, ...all);
  let max = Math.max(0, ...all);
  const pd = (max - min || 1) * 0.14;
  min -= pd;
  max += pd;
  const X = (i: number) => f.x0 + (nx === 1 ? 0.5 : i / (nx - 1)) * f.iw;
  const Y = (v: number) => f.y0 - ((v - min) / (max - min || 1)) * f.ih;
  const kids: ReactNode[] = axisLayer(f, min, max, null, true);
  kids.push(
    <text key="unit" x={f.x0} y={f.y1 - 6} style={{ font: "600 9px Inter, sans-serif", fill: "var(--subtle)" }}>
      {yUnit}
    </text>,
  );
  labels.forEach((lb, i) =>
    kids.push(
      <text key={`xl${i}`} x={X(i)} y={f.y0 + 17} textAnchor="middle" style={{ font: XLBL_FONT, fill: "var(--subtle)" }}>
        {lb}
      </text>,
    ),
  );
  // Вертикаль «база» у коэффициента 1 (если есть).
  const baseIdx = labels.findIndex((l) => l === "1" || l === "1,0" || l === "1,00");
  if (baseIdx >= 0) {
    kids.push(
      <line key="bl" x1={X(baseIdx)} y1={f.y1} x2={X(baseIdx)} y2={f.y0} stroke="var(--border-strong)" strokeWidth={1} strokeDasharray="3 4" />,
      <text key="blt" x={X(baseIdx)} y={f.y1 - 6} textAnchor="middle" style={{ font: "600 8.5px Inter, sans-serif", fill: "var(--subtle)" }}>
        база
      </text>,
    );
  }
  // Сначала неактивные серии (приглушённо), затем выбранная поверх.
  const drawn = [...series].sort((a) => (a.key === selectedKey ? 1 : -1));
  drawn.forEach((s) => {
    const sel = s.key === selectedKey;
    const pts = s.values.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
    kids.push(
      <polyline
        key={`l${s.key}`}
        points={pts}
        fill="none"
        stroke={s.color}
        strokeWidth={sel ? 2.8 : 1.5}
        opacity={selectedKey && !sel ? 0.32 : 1}
        strokeLinecap="round"
        strokeLinejoin="round"
      />,
    );
    if (sel) s.values.forEach((v, i) => kids.push(<circle key={`d${s.key}${i}`} cx={X(i)} cy={Y(v)} r={2.6} fill={s.color} />));
  });
  for (let i = 0; i < nx; i++)
    kids.push(
      <rect
        key={`hb${i}`}
        x={f.x0 + (i - 0.5) / (nx - 1 || 1) * f.iw}
        y={f.y1}
        width={f.iw / (nx - 1 || 1)}
        height={f.ih}
        fill="transparent"
        style={{ cursor: "crosshair" }}
        onMouseEnter={mkTip(
          `коэффициент ${labels[i]}`,
          series.map((s) => ({ label: s.label, val: fmtMoney(s.values[i] * 1e6), dot: s.color })),
        )}
        onMouseMove={mkTip(
          `коэффициент ${labels[i]}`,
          series.map((s) => ({ label: s.label, val: fmtMoney(s.values[i] * 1e6), dot: s.color })),
        )}
        onMouseLeave={clearTip}
      />,
    );
  return (
    <div data-chart-host style={{ position: "relative", height }}>
      <Svg p={p}>{kids}</Svg>
      {tip && <TipCard tip={tip} />}
    </div>
  );
}

/**
 * Гистограмма распределения (Монте-Карло, B5): столбцы по бинам, порог 0 —
 * красной вертикалью, цвет >0/<0, hover — диапазон и число попаданий.
 * Значения бинов — в млн (передаются уже поделёнными).
 */
export function HistogramChart({
  bins,
  height = 260,
}: {
  bins: Array<{ from: number; to: number; count: number }>;
  height?: number;
}) {
  const { tip, mkTip, clearTip } = useLocalTip();
  const p: P = { w: 900, h: 240, mL: 44, mR: 16, mT: 16, mB: 30 };
  const f = frame(p);
  if (bins.length === 0) return <EmptyChart p={p} />;
  const lo = bins[0].from;
  const hi = bins[bins.length - 1].to;
  const maxCount = Math.max(...bins.map((b) => b.count)) || 1;
  const X = (v: number) => f.x0 + ((v - lo) / (hi - lo || 1)) * f.iw;
  const Y = (c: number) => f.y0 - (c / maxCount) * f.ih;
  const kids: ReactNode[] = [];
  // Ось Y — count
  for (let k = 0; k <= 4; k++) {
    const c = (maxCount * k) / 4;
    const y = Y(c);
    kids.push(
      <line key={`g${k}`} x1={f.x0} y1={y} x2={f.x1} y2={y} stroke="var(--grid-line)" strokeWidth={1} />,
      <text key={`gl${k}`} x={f.x0 - 8} y={y + 3.5} textAnchor="end" style={{ font: AXIS_FONT, fill: "var(--subtle)" }}>
        {Math.round(c)}
      </text>,
    );
  }
  bins.forEach((b, i) => {
    const x0 = X(b.from);
    const x1 = X(b.to);
    const w = Math.max(x1 - x0 - 1, 1);
    const y = Y(b.count);
    const mid = (b.from + b.to) / 2;
    const color = mid >= 0 ? PAL.pos : PAL.neg;
    kids.push(
      <rect
        key={`b${i}`}
        x={x0}
        y={y}
        width={w}
        height={f.y0 - y}
        fill={color}
        style={{ cursor: "crosshair" }}
        onMouseEnter={mkTip(`NPV ${b.from.toFixed(1).replace(".", ",")}…${b.to.toFixed(1).replace(".", ",")} млн`, [
          { label: "Итераций", val: String(b.count), dot: color },
        ])}
        onMouseMove={mkTip(`NPV ${b.from.toFixed(1).replace(".", ",")}…${b.to.toFixed(1).replace(".", ",")} млн`, [
          { label: "Итераций", val: String(b.count), dot: color },
        ])}
        onMouseLeave={clearTip}
      />,
    );
  });
  // Порог NPV = 0
  if (lo < 0 && hi > 0) {
    const zx = X(0);
    kids.push(
      <line key="zero" x1={zx} y1={f.y1} x2={zx} y2={f.y0} stroke="var(--danger)" strokeWidth={1.4} strokeDasharray="5 4" />,
      <text key="zt" x={zx} y={f.y1 + 2} textAnchor="middle" style={{ font: "600 8.5px Inter, sans-serif", fill: "var(--danger)" }}>
        NPV = 0
      </text>,
    );
  }
  // Подписи X по краям и центру
  [lo, (lo + hi) / 2, hi].forEach((v, i) =>
    kids.push(
      <text
        key={`x${i}`}
        x={X(v)}
        y={f.y0 + 17}
        textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}
        style={{ font: XLBL_FONT, fill: "var(--subtle)" }}
      >
        {(v / 1).toFixed(1).replace(".", ",")}
      </text>,
    ),
  );
  return (
    <div data-chart-host style={{ position: "relative", height }}>
      <Svg p={p}>{kids}</Svg>
      {tip && <TipCard tip={tip} />}
    </div>
  );
}

/** Простой столбчатый график (± бары) с ховером. */
export function SimpleBarChart({
  items,
  height = 250,
  valueLabel = "Значение",
}: {
  items: Array<{ label: string; value: number }>;
  height?: number;
  valueLabel?: string;
}) {
  const { tip, mkTip, clearTip } = useLocalTip();
  const p: P = { w: 900, h: 240, mL: 52, mR: 16, mT: 16, mB: 30 };
  const f = frame(p);
  const n = items.length;
  if (n === 0) return <EmptyChart p={p} />;
  const vals = items.map((d) => d.value);
  let min = Math.min(0, ...vals);
  let max = Math.max(0, ...vals);
  const pd = (max - min || 1) * 0.12;
  min -= pd;
  max += pd;
  const Y = (v: number) => f.y0 - ((v - min) / (max - min || 1)) * f.ih;
  const band = f.iw / n;
  const bw = Math.min(band * 0.5, 56);
  const z = Y(0);
  const kids: ReactNode[] = axisLayer(f, min, max, null, true);
  items.forEach((d, i) => {
    const x = f.x0 + (i + 0.5) * band;
    const y = Y(d.value);
    const pos = d.value >= 0;
    kids.push(
      <rect
        key={`b${i}`}
        x={x - bw / 2}
        y={Math.min(y, z)}
        width={bw}
        height={Math.abs(y - z)}
        rx={3}
        fill={pos ? PAL.pos : PAL.neg}
        style={{ cursor: "crosshair" }}
        onMouseEnter={mkTip(d.label, [{ label: valueLabel, val: fmtMoney(d.value), dot: pos ? PAL.pos : PAL.neg }])}
        onMouseMove={mkTip(d.label, [{ label: valueLabel, val: fmtMoney(d.value), dot: pos ? PAL.pos : PAL.neg }])}
        onMouseLeave={clearTip}
      />,
      <text key={`n${i}`} x={x} y={f.y0 + 16} textAnchor="middle" style={{ font: "600 9.5px Inter, sans-serif", fill: "var(--subtle)" }}>
        {d.label.length > 16 ? d.label.slice(0, 15) + "…" : d.label}
      </text>,
    );
  });
  return (
    <div data-chart-host style={{ position: "relative", height }}>
      <Svg p={p}>{kids}</Svg>
      {tip && <TipCard tip={tip} />}
    </div>
  );
}
