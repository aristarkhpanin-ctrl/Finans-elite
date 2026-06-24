import type { ClipboardEvent } from "react";

interface Props {
  n: number;
  values: string[];
  label?: string;
  onChange: (values: string[]) => void;
}

/** Ввод помесячного ряда: n ячеек, быстрое «заполнить все», вставка из Excel и сумма ряда. */
export function MonthlySeries({ n, values, label, onChange }: Props) {
  const get = (i: number) => values[i] ?? "0";
  const setAt = (i: number, val: string) =>
    onChange(Array.from({ length: n }, (_, k) => (k === i ? val : get(k))));
  const fillAll = () => {
    const val = window.prompt("Значение для всех месяцев", get(0));
    if (val !== null) onChange(Array.from({ length: n }, () => val));
  };

  // Вставка из буфера (Excel/CSV): раскладываем значения по ячейкам начиная с текущей.
  // Разделители — табуляция/перенос строки/«;» (запятая остаётся десятичной).
  const onPaste = (i: number, e: ClipboardEvent<HTMLInputElement>) => {
    const parts = e.clipboardData.getData("text").trim().split(/[\t;\n\r]+/).filter((p) => p !== "");
    if (parts.length <= 1) return; // одно значение — обычная вставка
    e.preventDefault();
    onChange(Array.from({ length: n }, (_, k) =>
      k >= i && parts[k - i] !== undefined ? parts[k - i].replace(",", ".").trim() : get(k)));
  };

  const total = values.slice(0, n).reduce((s, v) => s + (Number(v) || 0), 0);

  return (
    <div className="series">
      <div className="series-label">
        {label && <span>{label}</span>}
        <span className="series-total" title="Сумма за период">
          Σ {total.toLocaleString("ru-RU", { maximumFractionDigits: 0 })}
        </span>
        <button type="button" className="link-btn" onClick={fillAll}>
          заполнить все
        </button>
      </div>
      <div className="series-row">
        {Array.from({ length: n }).map((_, i) => (
          <input
            key={i}
            className="series-cell"
            value={get(i)}
            title={`Месяц ${i + 1}`}
            onChange={(e) => setAt(i, e.target.value)}
            onPaste={(e) => onPaste(i, e)}
          />
        ))}
      </div>
    </div>
  );
}
