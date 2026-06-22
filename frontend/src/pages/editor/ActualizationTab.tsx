import type { Actualization } from "../../api/model";
import { MonthlySeries } from "../../components/MonthlySeries";
import { CheckField, NumberField } from "../../components/ui";

interface Props {
  n: number;
  actualization: Actualization;
  onChange: (a: Actualization) => void;
}

// Ключевые листовые строки Кэш-фло, по которым обычно вводят факт.
const LINES: [string, string][] = [
  ["C1", "Поступления от продаж"],
  ["C2", "Затраты на материалы"],
  ["C5", "Общие издержки"],
  ["C6", "Затраты на персонал"],
  ["C12", "Налоги"],
  ["C14", "Приобретение активов"],
];

export function ActualizationTab({ n, actualization, onChange }: Props) {
  const enabled = actualization.actual_until >= 0;
  const actuals = actualization.actuals ?? {};

  const setActual = (code: string, values: string[]) =>
    onChange({ ...actualization, actuals: { ...actuals, [code]: values } });

  return (
    <div>
      <h2>Актуализация (план-факт)</h2>
      <p className="muted" style={{ fontSize: 13 }}>
        Подставляет фактические значения Кэш-фло за прошедшие месяцы; на странице результатов
        появится сравнение план/факт.
      </p>

      <CheckField label="Учитывать фактические данные"
                  checked={enabled}
                  onChange={(on) => onChange({ ...actualization, actual_until: on ? 0 : -1 })} />

      {enabled && (
        <>
          <div className="form-grid" style={{ maxWidth: 320 }}>
            <NumberField label="Фактических месяцев (с начала)"
                         value={actualization.actual_until + 1}
                         onChange={(v) =>
                           onChange({ ...actualization, actual_until: Math.max(0, parseInt(v || "1", 10) - 1) })} />
          </div>
          {LINES.map(([code, label]) => (
            <MonthlySeries key={code} n={n} label={`${label} (${code})`}
                           values={actuals[code] ?? []}
                           onChange={(values) => setActual(code, values)} />
          ))}
        </>
      )}
    </div>
  );
}
