interface Props {
  n: number;
  values: string[];
  label?: string;
  onChange: (values: string[]) => void;
}

/** Ввод помесячного ряда: n ячеек + быстрое «заполнить все». */
export function MonthlySeries({ n, values, label, onChange }: Props) {
  const get = (i: number) => values[i] ?? "0";
  const setAt = (i: number, val: string) =>
    onChange(Array.from({ length: n }, (_, k) => (k === i ? val : get(k))));
  const fillAll = () => {
    const val = window.prompt("Значение для всех месяцев", get(0));
    if (val !== null) onChange(Array.from({ length: n }, () => val));
  };

  return (
    <div className="series">
      <div className="series-label">
        {label && <span>{label}</span>}
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
          />
        ))}
      </div>
    </div>
  );
}
