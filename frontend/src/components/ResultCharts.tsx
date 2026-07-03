import { useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import { line, type CalcResponse, type StatementOut } from "../api/calc";
import { fmtAxis, fmtMoney } from "../format";
import { axisLayer, CAT, EmptyChart, frame, monthLabels, PAL, Svg, type Frame, type P, type TipRow } from "./charts";

/**
 * Аналитические графики (макет «Этап 15»): 6 SVG-карточек на единой
 * графической теме — без сторонних чарт-библиотек. Палитра — токены
 * --chart-1..7 (живёт при смене темы), hover-тултипы с точками.
 * Примитивы (оси, рамка, пустое состояние) — в ./charts.
 */

interface Tip {
  card: string;
  x: number;
  y: number;
  hostW: number;
  title: string;
  rows: TipRow[];
}

const sumLine = (stmt: StatementOut, ...codes: string[]) =>
  codes.reduce((acc, code) => acc + line(stmt, code).reduce((s, v) => s + Number(v ?? 0), 0), 0);

export function ResultCharts({ result }: { result: CalcResponse }) {
  const [tip, setTip] = useState<Tip | null>(null);
  const n = result.n;

  const mkTip = (card: string, title: string, rows: TipRow[]) => (e: MouseEvent<SVGElement>) => {
    const host = (e.currentTarget as unknown as Element).closest("[data-chart-card]");
    if (!host) return;
    const r = host.getBoundingClientRect();
    setTip({ card, x: e.clientX - r.left, y: e.clientY - r.top, hostW: r.width, title, rows });
  };
  const clearTip = () => setTip(null);

  const hoverBand = (i: number, f: Frame, card: string, title: string, rows: TipRow[]) => (
    <rect
      key={`hb${i}`}
      x={f.x0 + (i / n) * f.iw}
      y={f.y1}
      width={f.iw / n}
      height={f.ih}
      fill="transparent"
      style={{ cursor: "crosshair" }}
      onMouseEnter={mkTip(card, title, rows)}
      onMouseMove={mkTip(card, title, rows)}
      onMouseLeave={clearTip}
    />
  );

  // ─── Данные из CalcResponse ────────────────────────────────────────────────
  const num = (arr: string[], i: number) => Number(arr[i] ?? 0);
  const c13 = line(result.cashflow, "C13");
  const c20 = line(result.cashflow, "C20");
  const c29 = line(result.cashflow, "C29");
  const i28 = line(result.income, "I28");
  const op = Array.from({ length: n }, (_, i) => num(c13, i));
  const inv = Array.from({ length: n }, (_, i) => num(c20, i));
  const cash = Array.from({ length: n }, (_, i) => num(c29, i));
  const net = Array.from({ length: n }, (_, i) => num(i28, i));

  let running = 0;
  const cum = op.map((v, i) => (running += v + inv[i]));

  const b = (code: string) => line(result.balance, code);
  const assetComps: Array<[string, number[]]> = [
    ["Деньги", Array.from({ length: n }, (_, i) => num(b("B1"), i))],
    ["Дебиторка", Array.from({ length: n }, (_, i) => num(b("B2"), i))],
    ["Запасы", Array.from({ length: n }, (_, i) => num(b("B3"), i) + num(b("B4"), i) + num(b("B5"), i))],
    ["Финвложения", Array.from({ length: n }, (_, i) => num(b("B6"), i))],
    ["Предоплаты", Array.from({ length: n }, (_, i) => num(b("B7"), i))],
    ["Внеоборотные", Array.from({ length: n }, (_, i) => num(b("B11"), i) + num(b("B17"), i) + num(b("B18"), i) + num(b("B19"), i))],
  ];

  const costItems: Array<[string, number]> = (
    [
      ["Материалы", sumLine(result.income, "I5")],
      ["Зарплата", sumLine(result.income, "I6", "I13", "I14", "I15")],
      ["Общие", sumLine(result.income, "I10", "I11", "I12")],
      ["Амортизация", sumLine(result.income, "I17")],
      ["Проценты", sumLine(result.income, "I18")],
      ["Налоги", sumLine(result.income, "I9", "I27")],
      ["Прочие", sumLine(result.income, "I21")],
    ] as Array<[string, number]>
  ).filter(([, v]) => v > 0);

  const v = result.valuation;
  const valMethods: Array<[string, number, string]> = (
    [
      ["Чистые активы", v.net_assets, "Чист. активы"],
      ["Метод Гордона", v.gordon_value, "Гордон"],
      ["DDM (дивиденды)", v.dividend_value, "DDM"],
      ["Мультипликаторы", v.earnings_multiple_value, "Мультипл."],
      ["Ликвидационная", v.liquidation_value, "Ликвид."],
    ] as Array<[string, string | null, string]>
  )
    .filter(([, val]) => val != null)
    .map(([name, val, short]) => [name, Number(val) / 1e6, short]);

  // ─── Построители графиков ──────────────────────────────────────────────────
  const Pfull: P = { w: 1100, h: 240, mL: 54, mR: 18, mT: 18, mB: 26 };
  const Phalf: P = { w: 560, h: 240, mL: 48, mR: 16, mT: 16, mB: 26 };
  const Ppie: P = { w: 340, h: 240, mL: 10, mR: 10, mT: 10, mB: 10 };
  const Pval: P = { w: 560, h: 240, mL: 34, mR: 14, mT: 26, mB: 36 };

  const chartCashflow = () => {
    const p = Pfull;
    const f = frame(p);
    let bmin = Math.min(0, ...op, ...inv);
    let bmax = Math.max(0, ...op, ...inv);
    const pd = (bmax - bmin) * 0.08;
    bmin -= pd;
    bmax += pd;
    const Yb = (val: number) => f.y0 - ((val - bmin) / (bmax - bmin || 1)) * f.ih;
    const cmin = Math.min(...cash) * 0.92;
    const cmax = Math.max(...cash) * 1.05;
    const Yc = (val: number) => f.y0 - ((val - cmin) / (cmax - cmin || 1)) * f.ih;
    const band = f.iw / n;
    const bw = Math.min(band * 0.3, 15);
    const z = Yb(0);
    const kids: ReactNode[] = axisLayer(f, bmin, bmax, monthLabels(n), true);
    for (let i = 0; i < n; i++) {
      const cx = f.x0 + (i + 0.5) * band;
      const oy = Yb(op[i]);
      const iy = Yb(inv[i]);
      kids.push(
        <rect key={`o${i}`} x={cx - bw - 1.5} y={Math.min(oy, z)} width={bw} height={Math.abs(oy - z)} rx={2} fill={PAL.op} />,
        <rect key={`i${i}`} x={cx + 1.5} y={Math.min(iy, z)} width={bw} height={Math.abs(iy - z)} rx={2} fill={PAL.inv} />,
      );
    }
    const pts = cash.map((val, i) => `${(f.x0 + (i + 0.5) * band).toFixed(1)},${Yc(val).toFixed(1)}`).join(" ");
    kids.push(<polyline key="cl" points={pts} fill="none" stroke={PAL.cash} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />);
    cash.forEach((val, i) =>
      kids.push(<circle key={`cc${i}`} cx={f.x0 + (i + 0.5) * band} cy={Yc(val)} r={2.3} fill={PAL.cash} />),
    );
    for (let i = 0; i < n; i++)
      kids.push(
        hoverBand(i, f, "cashflow", `М${i + 1}`, [
          { label: "Операционный", val: fmtMoney(op[i]), dot: PAL.op },
          { label: "Инвестиционный", val: fmtMoney(inv[i]), dot: PAL.inv },
          { label: "Остаток денег", val: fmtMoney(cash[i]), dot: PAL.cash },
        ]),
      );
    return <Svg p={p}>{kids}</Svg>;
  };

  const chartPayback = () => {
    const p = Phalf;
    const f = frame(p);
    let min = Math.min(0, ...cum);
    let max = Math.max(0, ...cum);
    const sp = max - min || 1;
    min -= sp * 0.1;
    max += sp * 0.1;
    const Y = (val: number) => f.y0 - ((val - min) / (max - min || 1)) * f.ih;
    const band = f.iw / n;
    const cx = (i: number) => f.x0 + (i + 0.5) * band;
    const zeroY = Y(0);
    const kids: ReactNode[] = axisLayer(f, min, max, monthLabels(n), false);
    const lp = cum.map((val, i) => `${cx(i).toFixed(1)},${Y(val).toFixed(1)}`);
    kids.push(
      <polygon
        key="ar"
        points={`${cx(0).toFixed(1)},${zeroY.toFixed(1)} ${lp.join(" ")} ${cx(n - 1).toFixed(1)},${zeroY.toFixed(1)}`}
        fill={PAL.pos}
        opacity={0.14}
      />,
      <polyline key="ln" points={lp.join(" ")} fill="none" stroke={PAL.pos} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />,
      <line key="z" x1={f.x0} y1={zeroY} x2={f.x1} y2={zeroY} stroke="var(--danger)" strokeWidth={1.4} strokeDasharray="6 4" />,
      <text key="zt" x={f.x1 - 2} y={zeroY - 5} textAnchor="end" style={{ font: "600 9px 'JetBrains Mono', monospace", fill: "var(--danger)" }}>
        0 — окупаемость
      </text>,
    );
    const pb = result.metrics.pb_months != null && result.metrics.pb_months <= n
      ? result.metrics.pb_months - 1
      : cum.findIndex((val) => val >= 0);
    if (pb >= 0 && pb < n) {
      const px = cx(pb);
      kids.push(
        <line key="pl" x1={px} y1={f.y1} x2={px} y2={f.y0} stroke={PAL.pos} strokeWidth={1.4} strokeDasharray="4 3" />,
        <circle key="pc" cx={px} cy={Y(cum[pb])} r={3.2} fill={PAL.pos} stroke="var(--surface)" strokeWidth={1.4} />,
        <text
          key="pt"
          x={px}
          y={f.y1 + 10}
          textAnchor={px > f.x0 + f.iw * 0.7 ? "end" : "middle"}
          style={{ font: "700 9.5px Inter, sans-serif", fill: PAL.pos }}
        >
          Окупаемость · М{pb + 1}
        </text>,
      );
    }
    for (let i = 0; i < n; i++)
      kids.push(hoverBand(i, f, "payback", `М${i + 1}`, [{ label: "Накопл. поток", val: fmtMoney(cum[i]), dot: PAL.pos }]));
    return <Svg p={p}>{kids}</Svg>;
  };

  const chartNet = () => {
    const p = Phalf;
    const f = frame(p);
    let min = Math.min(0, ...net);
    let max = Math.max(0, ...net);
    const pd = (max - min) * 0.1;
    min -= pd;
    max += pd;
    const Y = (val: number) => f.y0 - ((val - min) / (max - min || 1)) * f.ih;
    const band = f.iw / n;
    const bw = Math.min(band * 0.5, 20);
    const z = Y(0);
    const kids: ReactNode[] = axisLayer(f, min, max, monthLabels(n), true);
    for (let i = 0; i < n; i++) {
      const cx = f.x0 + (i + 0.5) * band;
      const y = Y(net[i]);
      kids.push(
        <rect key={`b${i}`} x={cx - bw / 2} y={Math.min(y, z)} width={bw} height={Math.abs(y - z)} rx={2.5} fill={net[i] >= 0 ? PAL.pos : PAL.neg} />,
      );
    }
    for (let i = 0; i < n; i++)
      kids.push(
        hoverBand(i, f, "net", `М${i + 1}`, [
          { label: "Чистая прибыль", val: fmtMoney(net[i]), dot: net[i] >= 0 ? PAL.pos : PAL.neg },
        ]),
      );
    return <Svg p={p}>{kids}</Svg>;
  };

  const chartAssets = () => {
    const p = Pfull;
    const f = frame(p);
    const comps = assetComps.map(([, arr]) => arr);
    const labels = assetComps.map(([l]) => l);
    const totals = Array.from({ length: n }, (_, i) => comps.reduce((a, c) => a + c[i], 0));
    const max = Math.max(...totals) * 1.05 || 1;
    const Y = (val: number) => f.y0 - (val / max) * f.ih;
    const band = f.iw / n;
    const bw = Math.min(band * 0.6, 26);
    const kids: ReactNode[] = axisLayer(f, 0, max, monthLabels(n), false);
    for (let i = 0; i < n; i++) {
      const cx = f.x0 + (i + 0.5) * band;
      let acc = 0;
      comps.forEach((c, k) => {
        const y0 = Y(acc);
        const y1 = Y(acc + c[i]);
        acc += c[i];
        kids.push(<rect key={`s${i}_${k}`} x={cx - bw / 2} y={y1} width={bw} height={Math.max(y0 - y1, 0)} fill={CAT[k]} />);
      });
    }
    for (let i = 0; i < n; i++) {
      const rows: TipRow[] = comps.map((c, k) => ({ label: labels[k], val: fmtMoney(c[i]), dot: CAT[k] }));
      rows.push({ label: "Суммарный актив", val: fmtMoney(totals[i]), dot: "var(--text)" });
      kids.push(hoverBand(i, f, "assets", `М${i + 1}`, rows));
    }
    return <Svg p={p}>{kids}</Svg>;
  };

  const chartCosts = () => {
    const p = Ppie;
    const total = costItems.reduce((a, [, val]) => a + val, 0) || 1;
    const cx = p.w * 0.42;
    const cy = p.h * 0.52;
    const r = Math.min(p.w * 0.3, p.h * 0.4);
    const ri = r * 0.58;
    let ang = -Math.PI / 2;
    const kids: ReactNode[] = [];
    costItems.forEach(([label, val], k) => {
      const a2 = ang + (val / total) * Math.PI * 2;
      const large = a2 - ang > Math.PI ? 1 : 0;
      const x1 = cx + r * Math.cos(ang);
      const y1 = cy + r * Math.sin(ang);
      const x2 = cx + r * Math.cos(a2);
      const y2 = cy + r * Math.sin(a2);
      const xi2 = cx + ri * Math.cos(a2);
      const yi2 = cy + ri * Math.sin(a2);
      const xi1 = cx + ri * Math.cos(ang);
      const yi1 = cy + ri * Math.sin(ang);
      const d = `M${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2} L${xi2},${yi2} A${ri},${ri} 0 ${large} 0 ${xi1},${yi1} Z`;
      const pct = ((val / total) * 100).toFixed(1).replace(".", ",");
      const rows: TipRow[] = [
        { label: "Сумма", val: fmtMoney(val), dot: CAT[k % CAT.length] },
        { label: "Доля", val: `${pct}%`, dot: CAT[k % CAT.length] },
      ];
      kids.push(
        <path
          key={`p${k}`}
          d={d}
          fill={CAT[k % CAT.length]}
          stroke="var(--surface)"
          strokeWidth={1.5}
          style={{ cursor: "crosshair" }}
          onMouseEnter={mkTip("costs", label, rows)}
          onMouseMove={mkTip("costs", label, rows)}
          onMouseLeave={clearTip}
        />,
      );
      ang = a2;
    });
    kids.push(
      <text key="c1" x={cx} y={cy - 2} textAnchor="middle" style={{ font: "700 16px 'JetBrains Mono', monospace", fill: "var(--text)" }}>
        {fmtAxis(total)}
      </text>,
      <text key="c2" x={cx} y={cy + 14} textAnchor="middle" style={{ font: "600 9px Inter, sans-serif", fill: "var(--subtle)" }}>
        издержки, ₽
      </text>,
    );
    return <Svg p={p}>{kids}</Svg>;
  };

  const chartValuation = () => {
    const p = Pval;
    const f = frame(p);
    const vals = valMethods.map(([, val]) => val);
    let min = Math.min(0, ...vals);
    let max = Math.max(0, ...vals);
    const pd = (max - min) * 0.16;
    min -= pd;
    max += pd;
    const Y = (val: number) => f.y0 - ((val - min) / (max - min || 1)) * f.ih;
    const count = valMethods.length;
    const band = f.iw / count;
    const bw = Math.min(band * 0.5, 48);
    const z = Y(0);
    const kids: ReactNode[] = axisLayer(f, min, max, null, true);
    kids.push(
      <text key="un" x={f.x0} y={f.y1 - 3} style={{ font: "600 9px Inter, sans-serif", fill: "var(--subtle)" }}>
        млн ₽
      </text>,
    );
    valMethods.forEach(([name, val, short], k) => {
      const cx = f.x0 + (k + 0.5) * band;
      const y = Y(val);
      const pos = val >= 0;
      const rows: TipRow[] = [{ label: "Оценка", val: fmtMoney(val * 1e6), dot: pos ? PAL.pos : PAL.neg }];
      kids.push(
        <rect
          key={`b${k}`}
          x={cx - bw / 2}
          y={Math.min(y, z)}
          width={bw}
          height={Math.abs(y - z)}
          rx={3}
          fill={pos ? PAL.pos : PAL.neg}
          style={{ cursor: "crosshair" }}
          onMouseEnter={mkTip("val", name, rows)}
          onMouseMove={mkTip("val", name, rows)}
          onMouseLeave={clearTip}
        />,
        <text
          key={`v${k}`}
          x={cx}
          y={pos ? y - 6 : y + 13}
          textAnchor="middle"
          style={{ font: "700 11px 'JetBrains Mono', monospace", fill: pos ? "var(--text)" : PAL.neg }}
        >
          {(val < 0 ? "−" : "") + Math.abs(val).toFixed(1).replace(".", ",")}
        </text>,
        <text key={`n${k}`} x={cx} y={f.y0 + 16} textAnchor="middle" style={{ font: "600 9.5px Inter, sans-serif", fill: "var(--subtle)" }}>
          {short}
        </text>,
      );
    });
    return <Svg p={p}>{kids}</Svg>;
  };

  // ─── Карточки ──────────────────────────────────────────────────────────────
  interface LegendItem {
    label: string;
    color: string;
    line?: boolean;
    value?: string;
  }

  const costTotal = costItems.reduce((a, [, val]) => a + val, 0) || 1;

  const cards: Array<{
    id: string;
    span2?: boolean;
    height: number;
    title: string;
    sub: string;
    legend: LegendItem[];
    empty: boolean;
    el: () => ReactNode;
    p: P;
  }> = [
    {
      id: "cashflow",
      span2: true,
      height: 250,
      p: Pfull,
      title: "Денежный поток",
      sub: "Операционный и инвестиционный поток · линия остатка денег",
      legend: [
        { label: "Операционный", color: PAL.op },
        { label: "Инвестиционный", color: PAL.inv },
        { label: "Остаток денег", color: PAL.cash, line: true },
      ],
      empty: op.every((x) => !x) && inv.every((x) => !x),
      el: chartCashflow,
    },
    {
      id: "payback",
      height: 250,
      p: Phalf,
      title: "Накопленный поток · окупаемость",
      sub: "Кумулятивный поток до финансирования · отметка PB",
      legend: [
        { label: "Накопленный поток", color: PAL.pos },
        { label: "Нулевая линия", color: "var(--danger)", line: true },
      ],
      empty: cum.every((x) => !x),
      el: chartPayback,
    },
    {
      id: "net",
      height: 250,
      p: Phalf,
      title: "Чистая прибыль",
      sub: "Помесячно · убыток — красным",
      legend: [
        { label: "Прибыль", color: PAL.pos },
        { label: "Убыток", color: PAL.neg },
      ],
      empty: net.every((x) => !x),
      el: chartNet,
    },
    {
      id: "assets",
      span2: true,
      height: 270,
      p: Pfull,
      title: "Структура активов",
      sub: "Накопительные столбцы · сумма = суммарный актив",
      legend: assetComps.map(([label], k) => ({ label, color: CAT[k] })),
      empty: assetComps.every(([, arr]) => arr.every((x) => !x)),
      el: chartAssets,
    },
    {
      id: "costs",
      height: 270,
      p: Ppie,
      title: "Структура издержек",
      sub: "За весь период проекта",
      legend: costItems.map(([label, val], k) => ({
        label,
        color: CAT[k % CAT.length],
        value: `${Math.round((val / costTotal) * 100)}%`,
      })),
      empty: costItems.length === 0,
      el: chartCosts,
    },
    {
      id: "val",
      height: 270,
      p: Pval,
      title: "Оценка бизнеса",
      sub: "Сравнение методов · отрицательные — красным",
      legend: [
        { label: "Положительная", color: PAL.pos },
        { label: "Отрицательная", color: PAL.neg },
      ],
      empty: valMethods.length === 0,
      el: chartValuation,
    },
  ];

  return (
    <div className="chart-grid">
      {cards.map((c) => (
        <div key={c.id} data-chart-card={c.id} className={"chart-card2" + (c.span2 ? " chart-card2--span2" : "")}>
          <div className="chart-card2__title">{c.title}</div>
          <div className="chart-card2__sub">{c.sub}</div>
          {!c.empty && (
            <div className="chart-legend">
              {c.legend.map((lg, k) => (
                <span key={k} className="chart-legend__item">
                  <span
                    style={{
                      width: lg.line ? 14 : 9,
                      height: lg.line ? 3 : 9,
                      borderRadius: lg.line ? 2 : 3,
                      background: lg.color,
                      flex: "none",
                    }}
                  />
                  {lg.label}
                  {lg.value && <span className="chart-legend__val">{lg.value}</span>}
                </span>
              ))}
            </div>
          )}
          <div style={{ height: c.height, marginTop: 10 }}>{c.empty ? <EmptyChart p={c.p} /> : c.el()}</div>
          {tip && tip.card === c.id && (
            <div
              className="chart-tip"
              style={{
                // не вылезать за правый край карточки
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
          )}
        </div>
      ))}
    </div>
  );
}
