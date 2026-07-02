import { useEffect, useState } from "react";
import { CubeHero } from "./CubeHero";

/**
 * Сплеш-экран загрузки (макет «Сплеш-экран загрузки (Modal)»): всегда тёмный,
 * куб 220–380px по устройству, wordmark, статус-строка с пульс-точкой и
 * прогресс с glow. Без пропсов прогресс идёт сам (асимптотически к 90%) —
 * для неопределённого ожидания (инициализация auth, ленивые чанки).
 */
const STAGES: Array<[number, string]> = [
  [30, "Загружаем ваше рабочее пространство…"],
  [85, "Синхронизируем финансовые модели…"],
  [101, "Готово — открываем рабочую область…"],
];

function labelFor(pct: number): string {
  for (const [limit, label] of STAGES) if (pct < limit) return label;
  return STAGES[STAGES.length - 1][1];
}

export function Splash({ progress, label }: { progress?: number; label?: string }) {
  const [auto, setAuto] = useState(8);

  useEffect(() => {
    if (progress !== undefined) return;
    const id = window.setInterval(() => {
      setAuto((p) => p + (90 - p) * 0.06);
    }, 200);
    return () => window.clearInterval(id);
  }, [progress]);

  const pct = Math.max(0, Math.min(100, Math.round(progress ?? auto)));

  return (
    <div className="splash">
      <div className="splash__cube">
        <CubeHero backdrop="transparent" />
      </div>
      <div className="splash__wordmark">
        Финанс<span>-Элит</span>
      </div>
      <div className="splash__label" role="status">
        <span className="splash__dot" />
        {label ?? labelFor(pct)}
      </div>
      <div className="splash__track">
        <div className="splash__bar" style={{ width: `${pct}%` }} />
      </div>
      <div className="splash__pct">{pct}%</div>
    </div>
  );
}
