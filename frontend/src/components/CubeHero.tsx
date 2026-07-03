import React, { useEffect, useRef, useState } from "react";

/**
 * «Зелёный куб» — анимированная 3D-сцена из макета `Cube Hero.dc.html`.
 *
 * Родитель должен задавать размеры (компонент растягивается на 100%×100%);
 * все внутренние размеры — в cqmin относительно контейнера (container-type:size).
 * При `prefers-reduced-motion: reduce` рендерится статичный кадр:
 * без RAF-цикла, CSS-анимаций, скан-развёртки и ударной волны.
 */
export interface CubeHeroProps {
  /** Пара акцентов [основной, глубокий]; по умолчанию ["#7FEE64", "#1FAE68"]. */
  accent?: [string, string];
  /** «scene» — тёмный фон с виньеткой; «transparent» — только куб. */
  backdrop?: "scene" | "transparent";
  /** Пол-сетка и мерцающие звёзды вокруг сцены. */
  showEnvironment?: boolean;
  /** Орбита из 12 светящихся точек. */
  showOrbit?: boolean;
  motionSpeed?: "calm" | "normal" | "energetic";
  /** Наклон куба за курсором. */
  pointerTilt?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

const SPEED: Record<string, number> = { calm: 0.62, normal: 1, energetic: 1.55 };
const EASE = "cubic-bezier(0.37,0,0.63,1)";
const H = 18.571; // половина ребра внешнего куба, cqmin
const CH = 7.714; // половина ребра ядра, cqmin

function hexToRgb(hex: string): string {
  const h = (hex || "#7FEE64").replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.substring(i, i + 2), 16)).join(",");
}

const q = (n: number) => `${n}cqmin`;
/** rgba от CSS-переменной акцента: v="accent" | "accent2". */
const va = (v: string, alpha: number) => `rgba(var(--${v}-rgb),${alpha})`;
const vc = (v: string) => `rgb(var(--${v}-rgb))`;
/** animation с длительностью/задержкой, масштабируемыми через --speed. */
const anim = (name: string, dur: number, delay: number) =>
  `${name} calc(${dur}s / var(--speed)) ${EASE} calc(${delay}s / var(--speed)) infinite`;

// ─── Данные сцены (значения 1:1 из макета) ────────────────────────────────────

/** Звёзды: [left %, top %, размер, длительность, задержка, яркая]. */
const STARS: Array<[number, number, number, number, number, boolean]> = [
  [8, 15, 0.429, 4.2, 0, true],
  [92, 20, 0.286, 3.6, 0.5, true],
  [15, 80, 0.286, 4.8, 1, true],
  [85, 75, 0.429, 3.9, 1.5, true],
  [5, 50, 0.286, 4.4, 2, false],
  [95, 55, 0.429, 3.4, 2.5, false],
  [25, 10, 0.286, 4.6, 3, false],
  [75, 90, 0.286, 3.7, 3.5, false],
];

/** Орбита: [размер, translateZ, translateY, длительность glint]; угол = i·30°, задержка = i·0.3s. */
const ORBIT: Array<[number, number, number, number]> = [
  [0.857, 33.571, 0, 2.2],
  [0.714, 36.429, -2.571, 2.6],
  [1, 33.571, 2.286, 2.4],
  [0.714, 36.429, -1.429, 2.8],
  [0.857, 33.571, 2.571, 2.3],
  [0.714, 36.429, -2.286, 2.7],
  [1, 33.571, 0, 2.5],
  [0.714, 36.429, 2, 2.9],
  [0.857, 33.571, -2.571, 2.2],
  [0.714, 36.429, 1.429, 2.6],
  [1, 33.571, -2, 2.4],
  [0.714, 36.429, 2.571, 2.8],
];
const ORBIT_BLUR: Record<number, number> = { 0.857: 1.286, 0.714: 1.143, 1: 1.429 };

interface FaceSpec {
  transform: string;
  grad: string;
  grid: number;
  border: number;
  shadow: string;
  nodes?: Array<[number, number, number, number]>; // [left, top, dur, delay]
  scanDelay?: number;
}

const grad = (a2: number, a1: number, dark: string, stop = 48) =>
  `linear-gradient(135deg, ${va("accent2", a2)} 0%, ${va("accent", a1)} ${stop}%, ${dark} 100%)`;

const FACES: FaceSpec[] = [
  {
    transform: `translateZ(${q(H)})`,
    grad: grad(0.22, 0.14, "rgba(6,26,19,0.30)"),
    grid: 0.16,
    border: 0.5,
    shadow: `0 0 ${q(3.714)} ${va("accent", 0.32)}, inset 0 0 ${q(5.143)} ${va("accent", 0.12)}, inset 0 ${q(0.143)} ${q(0.143)} rgba(255,255,255,0.28)`,
    nodes: [
      [9.286, 9.286, 2.3, 0],
      [27.857, 27.857, 2.7, 0.4],
    ],
    scanDelay: 0,
  },
  {
    transform: `rotateY(180deg) translateZ(${q(H)})`,
    grad: grad(0.12, 0.09, "rgba(5,22,16,0.36)"),
    grid: 0.13,
    border: 0.36,
    shadow: `0 0 ${q(2.857)} ${va("accent", 0.2)}, inset 0 0 ${q(4.286)} ${va("accent", 0.09)}`,
    nodes: [
      [27.857, 9.286, 2.3, 1.6],
      [9.286, 27.857, 2.7, 2.0],
    ],
    scanDelay: 3.2,
  },
  {
    transform: `rotateY(90deg) translateZ(${q(H)})`,
    grad: grad(0.19, 0.12, "rgba(6,26,19,0.33)"),
    grid: 0.15,
    border: 0.46,
    shadow: `0 0 ${q(3.429)} ${va("accent", 0.28)}, inset 0 0 ${q(4.857)} ${va("accent", 0.11)}, inset 0 ${q(0.143)} ${q(0.143)} rgba(255,255,255,0.25)`,
    nodes: [
      [18.571, 9.286, 2.5, 0.8],
      [9.286, 27.857, 2.9, 1.2],
    ],
    scanDelay: 1.6,
  },
  {
    transform: `rotateY(-90deg) translateZ(${q(H)})`,
    grad: grad(0.15, 0.1, "rgba(6,24,17,0.36)"),
    grid: 0.14,
    border: 0.4,
    shadow: `0 0 ${q(3.143)} ${va("accent", 0.24)}, inset 0 0 ${q(4.571)} ${va("accent", 0.1)}`,
    nodes: [
      [18.571, 27.857, 2.5, 2.4],
      [27.857, 18.571, 2.9, 2.8],
    ],
    scanDelay: 4.8,
  },
  {
    transform: `rotateX(90deg) translateZ(${q(H)})`,
    grad: grad(0.36, 0.22, "rgba(10,40,30,0.16)", 55),
    grid: 0.2,
    border: 0.62,
    shadow: `0 0 ${q(4.571)} ${va("accent", 0.4)}, inset 0 0 ${q(6)} ${va("accent", 0.2)}, inset 0 ${q(0.143)} ${q(0.143)} rgba(255,255,255,0.35)`,
  },
  {
    transform: `rotateX(-90deg) translateZ(${q(H)})`,
    grad: grad(0.08, 0.06, "rgba(3,14,10,0.42)", 55),
    grid: 0.08,
    border: 0.28,
    shadow: `0 0 ${q(2.571)} ${va("accent", 0.18)}, inset 0 0 ${q(4)} ${va("accent", 0.08)}`,
  },
];

/** Угловые блики: [±x, ±y, ±z, основной акцент?, длительность]; задержка = i·0.4s. */
const CORNERS: Array<[number, number, number, boolean, number]> = [
  [1, -1, 1, true, 3.0],
  [1, -1, -1, false, 3.3],
  [-1, -1, 1, false, 2.8],
  [-1, -1, -1, true, 3.1],
  [1, 1, 1, false, 2.9],
  [1, 1, -1, true, 3.4],
  [-1, 1, 1, true, 2.7],
  [-1, 1, -1, false, 3.2],
];

/** 12 рёбер куба с полуребром h: [вертикальное?, transform]. */
function edges(h: number): Array<[boolean, string]> {
  const t = (x: number, y: number, z: number, rot = "") =>
    `translate3d(${q(x)},${q(y)},${q(z)})${rot ? " " + rot : ""}`;
  return [
    [false, t(0, -h, -h)],
    [false, t(0, -h, h)],
    [false, t(0, h, -h)],
    [false, t(0, h, h)],
    [true, t(-h, 0, -h)],
    [true, t(-h, 0, h)],
    [true, t(h, 0, -h)],
    [true, t(h, 0, h)],
    [false, t(-h, -h, 0, "rotateY(90deg)")],
    [false, t(-h, h, 0, "rotateY(90deg)")],
    [false, t(h, -h, 0, "rotateY(90deg)")],
    [false, t(h, h, 0, "rotateY(90deg)")],
  ];
}

const CORE_FACES = [
  `translateZ(${q(CH)})`,
  `rotateY(180deg) translateZ(${q(CH)})`,
  `rotateY(90deg) translateZ(${q(CH)})`,
  `rotateY(-90deg) translateZ(${q(CH)})`,
  `rotateX(90deg) translateZ(${q(CH)})`,
  `rotateX(-90deg) translateZ(${q(CH)})`,
];

// ─── Стили-конструкторы ───────────────────────────────────────────────────────

const abs: React.CSSProperties = { position: "absolute" };
const centered: React.CSSProperties = { ...abs, top: "50%", left: "50%" };

function faceStyle(f: FaceSpec, side: number, half: number, gridStep: number): React.CSSProperties {
  return {
    ...centered,
    width: q(side),
    height: q(side),
    margin: `-${q(half)} 0 0 -${q(half)}`,
    borderRadius: q(1.429),
    overflow: "hidden",
    backfaceVisibility: "hidden",
    transform: f.transform,
    backgroundImage: `${f.grad}, linear-gradient(${va("accent", f.grid)} ${q(0.143)}, transparent ${q(0.143)}), linear-gradient(90deg, ${va("accent", f.grid)} ${q(0.143)}, transparent ${q(0.143)})`,
    backgroundSize: `100% 100%, ${q(gridStep)} ${q(gridStep)}, ${q(gridStep)} ${q(gridStep)}`,
    border: `${q(0.143)} solid ${va("accent", f.border)}`,
    boxShadow: f.shadow,
  };
}

function edgeStyle(vertical: boolean, transform: string, outer: boolean): React.CSSProperties {
  const len = outer ? 37.143 : 15.429;
  const thick = outer ? 0.714 : 0.429;
  const color = outer ? "accent" : "accent2";
  return {
    ...centered,
    width: vertical ? q(thick) : q(len),
    height: vertical ? q(len) : q(thick),
    margin: vertical ? `-${q(len / 2)} 0 0 -${q(thick / 2)}` : `-${q(thick / 2)} 0 0 -${q(len / 2)}`,
    borderRadius: q(outer ? 0.429 : 0.286),
    background: vc(color),
    boxShadow: outer
      ? `0 0 ${q(1.429)} ${q(0.286)} ${va(color, 0.9)}, 0 0 ${q(3.429)} ${va(color, 0.45)}`
      : `0 0 ${q(0.857)} ${q(0.143)} ${va(color, 0.85)}, 0 0 ${q(2)} ${va(color, 0.45)}`,
    opacity: outer ? 0.85 : 0.9,
    transform,
  };
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

// ─── Компонент ────────────────────────────────────────────────────────────────

export function CubeHero({
  accent,
  backdrop = "scene",
  showEnvironment = true,
  showOrbit = true,
  motionSpeed = "normal",
  pointerTilt = true,
  className,
  style,
}: CubeHeroProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const rigRef = useRef<HTMLDivElement>(null);
  const cubeSpinRef = useRef<HTMLDivElement>(null);
  const coreSpinRef = useRef<HTMLDivElement>(null);
  const state = useRef({ start: 0, tx: 0, ty: 0, cx: 0, cy: 0 });
  const reduced = usePrefersReducedMotion();

  const [c1, c2] = accent ?? ["#7FEE64", "#1FAE68"];
  const speed = SPEED[motionSpeed] ?? 1;
  const showSceneBg = backdrop !== "transparent";

  useEffect(() => {
    if (reduced) return;
    const stage = stageRef.current;
    const s = state.current;
    if (!s.start) s.start = performance.now();

    const onMove = (e: PointerEvent) => {
      if (!stage) return;
      const r = stage.getBoundingClientRect();
      s.tx = ((e.clientX - r.left) / r.width - 0.5) * 24;
      s.ty = ((e.clientY - r.top) / r.height - 0.5) * 24;
    };
    const onLeave = () => {
      s.tx = 0;
      s.ty = 0;
    };
    if (pointerTilt && stage) {
      stage.addEventListener("pointermove", onMove);
      stage.addEventListener("pointerleave", onLeave);
    }

    let raf = 0;
    const loop = (now: number) => {
      const t = now - s.start;
      const tx = pointerTilt ? s.tx : 0;
      const ty = pointerTilt ? s.ty : 0;
      s.cx += (tx - s.cx) * 0.07;
      s.cy += (ty - s.cy) * 0.07;

      const spinPeriod = 32000 / speed;
      const spinAngle = ((t % spinPeriod) / spinPeriod) * 360;
      const corePeriod = 17000 / speed;
      const coreAngle = ((t % corePeriod) / corePeriod) * 360;
      const bobPeriod = 6500 / speed;
      const bobPhase = ((t % bobPeriod) / bobPeriod) * Math.PI * 2;
      const bobY = -1.142857 + 1.142857 * Math.cos(bobPhase);

      const p = Math.min(1, t / 1500);
      const ease = 1 - Math.pow(1 - p, 3);
      const scaleVal = 0.7 + 0.3 * ease;
      const introY = 6.571429 * (1 - ease);

      // Порядок шагов повторяет вложенность обёрток макета
      // (bob → pointer-tilt → intro → spin); повороты вокруг разных осей
      // не коммутируют, поэтому углы нельзя складывать в один.
      const rig = rigRef.current;
      if (rig) {
        rig.style.opacity = ease.toFixed(3);
        rig.style.transform =
          `translateY(${bobY.toFixed(3)}cqmin) ` +
          `rotateX(${(-s.cy).toFixed(2)}deg) rotateY(${s.cx.toFixed(2)}deg) ` +
          `scale(${scaleVal.toFixed(3)}) translateY(${introY.toFixed(3)}cqmin)`;
      }
      const cube = cubeSpinRef.current;
      if (cube) cube.style.transform = `rotateX(22deg) rotateY(${spinAngle.toFixed(2)}deg)`;
      const core = coreSpinRef.current;
      if (core) core.style.transform = `rotateX(14deg) rotateY(${coreAngle.toFixed(2)}deg)`;

      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      if (pointerTilt && stage) {
        stage.removeEventListener("pointermove", onMove);
        stage.removeEventListener("pointerleave", onLeave);
      }
    };
  }, [reduced, speed, pointerTilt]);

  const stageStyle = {
    position: "relative",
    width: "100%",
    height: "100%",
    overflow: "hidden",
    containerType: "size",
    "--accent-rgb": hexToRgb(c1),
    "--accent2-rgb": hexToRgb(c2),
    "--speed": String(speed),
    ...style,
  } as React.CSSProperties;

  return (
    <div
      ref={stageRef}
      className={(reduced ? "cube-static" : "") + (className ? " " + className : "")}
      style={stageStyle}
      aria-hidden="true"
    >
      {showSceneBg && (
        <div
          style={{
            ...abs,
            inset: 0,
            background:
              "radial-gradient(ellipse 80% 60% at 50% 36%, #0d1813 0%, #070b09 45%, #030505 100%)",
            pointerEvents: "none",
          }}
        />
      )}

      <div
        style={{
          ...abs,
          top: "34%",
          left: "50%",
          width: q(131.429),
          height: q(131.429),
          transform: "translate(-50%,-50%)",
          background: `radial-gradient(circle, ${va("accent", 0.16)} 0%, ${va("accent", 0.05)} 35%, transparent 70%)`,
          filter: `blur(${q(0.857)})`,
          opacity: reduced ? 1 : 0,
          animation: reduced ? undefined : "cube-scene-in 2.4s ease-out both",
          pointerEvents: "none",
        }}
      />

      {showEnvironment && (
        <>
          <div
            style={{
              ...abs,
              bottom: 0,
              left: 0,
              width: "100%",
              height: "46%",
              backgroundImage: `linear-gradient(${va("accent", 0.08)} ${q(0.143)}, transparent ${q(0.143)}), linear-gradient(90deg, ${va("accent", 0.08)} ${q(0.143)}, transparent ${q(0.143)})`,
              backgroundSize: `${q(6.857)} ${q(6.857)}`,
              transform: `perspective(${q(60)}) rotateX(72deg) scale(2.2)`,
              transformOrigin: "bottom",
              maskImage: "linear-gradient(to top, black, transparent)",
              WebkitMaskImage: "linear-gradient(to top, black, transparent)",
              opacity: reduced ? 0.55 : 0,
              animation: reduced ? undefined : "cube-floor-in 2.4s ease-out 0.2s both",
              pointerEvents: "none",
            }}
          />
          {STARS.map(([left, top, size, dur, delay, bright], i) => (
            <div
              key={i}
              style={{
                ...abs,
                left: `${left}%`,
                top: `${top}%`,
                width: q(size),
                height: q(size),
                borderRadius: "50%",
                background: `rgba(225,255,240,${bright ? 0.7 : 0.6})`,
                boxShadow: `0 0 ${q(size > 0.4 ? 0.857 : 0.714)} ${va("accent", bright ? 0.6 : 0.5)}`,
                animation: `cube-star ${dur}s ${EASE} ${delay}s infinite`,
              }}
            />
          ))}
        </>
      )}

      <div style={{ ...centered, margin: `-${q(50)} 0 0 -${q(50)}`, width: q(100), height: q(100) }}>
        {showOrbit && (
          <div
            style={{
              ...centered,
              width: 0,
              height: 0,
              transformStyle: "preserve-3d",
              opacity: reduced ? 1 : 0,
              animation: reduced
                ? undefined
                : "cube-orbit calc(24s / var(--speed)) linear infinite, cube-scene-in 1.6s ease-out 0.3s both",
            }}
          >
            {ORBIT.map(([size, z, y, dur], i) => {
              const color = i % 2 === 0 ? "accent" : "accent2";
              return (
                <div
                  key={i}
                  style={{
                    ...abs,
                    top: 0,
                    left: 0,
                    width: q(size),
                    height: q(size),
                    transform: `rotateY(${i * 30}deg) translateZ(${q(z)}) translateY(${q(y)}) translate(-50%,-50%)`,
                  }}
                >
                  <div
                    style={{
                      ...abs,
                      inset: 0,
                      borderRadius: "50%",
                      background: vc(color),
                      boxShadow: `0 0 ${q(ORBIT_BLUR[size])} ${q(0.286)} ${va(color, 0.8)}`,
                      animation: anim("cube-glint", dur, i * 0.3),
                    }}
                  />
                </div>
              );
            })}
          </div>
        )}

        <div
          ref={rigRef}
          style={{
            ...centered,
            margin: `-${q(H)} 0 0 -${q(H)}`,
            width: q(37.143),
            height: q(37.143),
            transformStyle: "preserve-3d",
            opacity: reduced ? 1 : 0,
          }}
        >
          {!reduced && (
            <div
              style={{
                ...centered,
                width: q(48.571),
                height: q(48.571),
                margin: `-${q(24.286)} 0 0 -${q(24.286)}`,
                borderRadius: "50%",
                border: `${q(0.214)} solid ${va("accent", 0.55)}`,
                opacity: 0,
                animation: "cube-shockwave 1.8s cubic-bezier(0.16,1,0.3,1) 0.2s both",
                pointerEvents: "none",
              }}
            />
          )}

          <div
            ref={cubeSpinRef}
            style={{
              ...abs,
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
              transformStyle: "preserve-3d",
              transform: reduced ? "rotateX(22deg) rotateY(28deg)" : "rotateX(22deg)",
            }}
          >
            {FACES.map((f, i) => (
              <div key={i} style={faceStyle(f, 37.143, H, 9.286)}>
                {f.nodes?.map(([x, y, dur, delay], j) => (
                  <div
                    key={j}
                    style={{
                      ...abs,
                      left: q(x),
                      top: q(y),
                      width: q(1),
                      height: q(1),
                      margin: `-${q(0.5)} 0 0 -${q(0.5)}`,
                    }}
                  >
                    <div
                      style={{
                        ...abs,
                        inset: 0,
                        borderRadius: "50%",
                        background: vc("accent"),
                        boxShadow: `0 0 ${q(1.429)} ${q(0.429)} ${va("accent", 0.85)}`,
                        animation: anim("cube-node", dur, delay),
                      }}
                    />
                  </div>
                ))}
                {!reduced && f.scanDelay !== undefined && (
                  <div
                    style={{
                      ...abs,
                      left: 0,
                      right: 0,
                      top: 0,
                      height: "45%",
                      background:
                        "linear-gradient(to bottom, transparent, rgba(225,255,240,0.4), transparent)",
                      animation: anim("cube-scan", 6.5, f.scanDelay),
                      pointerEvents: "none",
                    }}
                  />
                )}
              </div>
            ))}

            {CORNERS.map(([sx, sy, sz, primary, dur], i) => {
              const color = primary ? "accent" : "accent2";
              return (
                <div
                  key={i}
                  style={{
                    ...centered,
                    width: q(1.429),
                    height: q(1.429),
                    transform: `translate3d(${q(sx * H)},${q(sy * H)},${q(sz * H)}) translate(-50%,-50%)`,
                  }}
                >
                  <div
                    style={{
                      ...abs,
                      inset: 0,
                      borderRadius: "50%",
                      background: `radial-gradient(circle, rgba(255,255,255,0.95) 0%, ${vc(color)} 45%, ${va(color, 0)} 100%)`,
                      boxShadow: `0 0 ${q(1.714)} ${q(0.286)} ${va(color, 0.85)}`,
                      animation: anim("cube-glint", dur, i * 0.4),
                    }}
                  />
                </div>
              );
            })}

            {edges(H).map(([vertical, transform], i) => (
              <div key={i} style={edgeStyle(vertical, transform, true)} />
            ))}
          </div>

          <div
            ref={coreSpinRef}
            style={{
              ...centered,
              margin: `-${q(CH)} 0 0 -${q(CH)}`,
              width: q(15.429),
              height: q(15.429),
              transformStyle: "preserve-3d",
              transform: reduced ? "rotateX(14deg) rotateY(40deg)" : "rotateX(14deg)",
            }}
          >
            {CORE_FACES.map((transform, i) => (
              <div
                key={i}
                style={{
                  ...centered,
                  width: q(15.429),
                  height: q(15.429),
                  margin: `-${q(CH)} 0 0 -${q(CH)}`,
                  borderRadius: q(0.571),
                  backfaceVisibility: "hidden",
                  transform,
                  background: va("accent2", 0.2),
                  border: `${q(0.143)} solid ${va("accent2", 0.45)}`,
                  boxShadow: `0 0 ${q(2.286)} ${va("accent2", 0.4)}, inset 0 0 ${q(2.286)} ${va("accent2", 0.3)}`,
                }}
              />
            ))}
            {edges(CH).map(([vertical, transform], i) => (
              <div key={i} style={edgeStyle(vertical, transform, false)} />
            ))}
          </div>

          <div
            style={{
              ...centered,
              margin: `-${q(5.143)} 0 0 -${q(5.143)}`,
              width: q(10.286),
              height: q(10.286),
              borderRadius: "50%",
              background: `radial-gradient(circle, rgba(255,255,255,0.9) 0%, ${va("accent2", 0.75)} 32%, ${va("accent2", 0.18)} 65%, transparent 100%)`,
              animation: anim("cube-core-glow", 3.4, 0),
              pointerEvents: "none",
            }}
          />
        </div>
      </div>

      {showSceneBg && (
        <div
          style={{
            ...abs,
            inset: 0,
            background:
              "radial-gradient(ellipse 70% 70% at 50% 50%, transparent 55%, rgba(0,0,0,0.65) 100%)",
            pointerEvents: "none",
          }}
        />
      )}
    </div>
  );
}
