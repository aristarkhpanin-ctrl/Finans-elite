import { useEffect, useState } from "react";
import { CubeHero } from "./CubeHero";
import { currentProduct, PRODUCTS, type Product } from "./product";

/**
 * Сплеш-экран загрузки (макеты «Сплеш-экран загрузки (Modal)» и «Финанс Аудит —
 * Сплеш-экран загрузки»): всегда тёмный, куб 220–380px по устройству, wordmark,
 * статус-строка с пульс-точкой и прогресс с glow. Без пропсов прогресс идёт сам
 * (асимптотически к 90%) — для неопределённого ожидания (инициализация auth,
 * ленивые чанки).
 *
 * Марка и статус-строка следуют продукту: сплеш рисуется раньше каркаса и до
 * маршрутизации, поэтому продукт берётся из `currentProduct()`, а не из роутера.
 * Зелёная заставка со словом «-Элит» перед фиолетовым делом читалась бы как
 * загрузка не того продукта.
 */
const STAGES: Record<Product, Array<[number, string]>> = {
  business: [
    [30, "Загружаем ваше рабочее пространство…"],
    [85, "Синхронизируем финансовые модели…"],
    [101, "Готово — открываем рабочую область…"],
  ],
  audit: [
    [30, "Загружаем ваше рабочее пространство…"],
    [85, "Поднимаем отчётность по делам…"],
    [101, "Готово — открываем рабочую область…"],
  ],
};

function labelFor(product: Product, pct: number): string {
  const stages = STAGES[product];
  for (const [limit, label] of stages) if (pct < limit) return label;
  return stages[stages.length - 1][1];
}

export function Splash({ progress, label }: { progress?: number; label?: string }) {
  const [product] = useState(currentProduct);
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
    <div className={"splash" + (product === "audit" ? " splash--audit" : "")}>
      <div className="splash__cube">
        <CubeHero accent={PRODUCTS[product].cubeAccent} backdrop="transparent" />
      </div>
      <div className="splash__wordmark">
        Финанс<span>{PRODUCTS[product].brand}</span>
      </div>
      <div className="splash__label" role="status">
        <span className="splash__dot" />
        {label ?? labelFor(product, pct)}
      </div>
      <div className="splash__track">
        <div className="splash__bar" style={{ width: `${pct}%` }} />
      </div>
      <div className="splash__pct">{pct}%</div>
    </div>
  );
}
