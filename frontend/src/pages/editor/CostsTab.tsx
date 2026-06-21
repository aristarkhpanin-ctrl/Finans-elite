import {
  COST_FUNCTION_LABELS,
  type CostFunction,
  type DirectCostKind,
  type DirectCostLine,
  type FixedCostLine,
  type OperatingPlan,
} from "../../api/model";
import { MonthlySeries } from "../../components/MonthlySeries";
import { Button } from "../../components/ui";

interface Props {
  n: number;
  operating: OperatingPlan;
  onChange: (op: OperatingPlan) => void;
}

export function CostsTab({ n, operating, onChange }: Props) {
  const direct = operating.direct_costs;
  const fixed = operating.fixed_costs;

  const addDirect = () =>
    onChange({
      ...operating,
      direct_costs: [...direct, { name: "Материалы", kind: "materials", amount: [], payment_delay_months: 0, stock_lead_months: 0 }],
    });
  const updateDirect = (i: number, patch: Partial<DirectCostLine>) =>
    onChange({ ...operating, direct_costs: direct.map((d, k) => (k === i ? { ...d, ...patch } : d)) });
  const removeDirect = (i: number) =>
    onChange({ ...operating, direct_costs: direct.filter((_, k) => k !== i) });

  const addFixed = () =>
    onChange({
      ...operating,
      fixed_costs: [...fixed, { name: "Издержка", function: "admin", amount: [], payment_delay_months: 0 }],
    });
  const updateFixed = (i: number, patch: Partial<FixedCostLine>) =>
    onChange({ ...operating, fixed_costs: fixed.map((f, k) => (k === i ? { ...f, ...patch } : f)) });
  const removeFixed = (i: number) =>
    onChange({ ...operating, fixed_costs: fixed.filter((_, k) => k !== i) });

  return (
    <div>
      <div className="section-head">
        <h2>Прямые издержки</h2>
        <Button onClick={addDirect}>+ Прямая издержка</Button>
      </div>
      {direct.map((d, i) => (
        <div className="row-card" key={i}>
          <div className="row-head">
            <input className="input grow" value={d.name} onChange={(e) => updateDirect(i, { name: e.target.value })} />
            <select className="select" value={d.kind}
                    onChange={(e) => updateDirect(i, { kind: e.target.value as DirectCostKind })}>
              <option value="materials">Материалы</option>
              <option value="piece_wages">Сдельная зарплата</option>
            </select>
            <Button variant="ghost" onClick={() => removeDirect(i)}>Удалить</Button>
          </div>
          <MonthlySeries n={n} label="Сумма" values={d.amount} onChange={(amount) => updateDirect(i, { amount })} />
        </div>
      ))}

      <div className="section-head" style={{ marginTop: 22 }}>
        <h2>Постоянные издержки</h2>
        <Button onClick={addFixed}>+ Постоянная издержка</Button>
      </div>
      {fixed.map((f, i) => (
        <div className="row-card" key={i}>
          <div className="row-head">
            <input className="input grow" value={f.name} onChange={(e) => updateFixed(i, { name: e.target.value })} />
            <select className="select" value={f.function}
                    onChange={(e) => updateFixed(i, { function: e.target.value as CostFunction })}>
              {Object.entries(COST_FUNCTION_LABELS).map(([k, label]) => (
                <option key={k} value={k}>{label}</option>
              ))}
            </select>
            <Button variant="ghost" onClick={() => removeFixed(i)}>Удалить</Button>
          </div>
          <MonthlySeries n={n} label="Сумма" values={f.amount} onChange={(amount) => updateFixed(i, { amount })} />
        </div>
      ))}
    </div>
  );
}
