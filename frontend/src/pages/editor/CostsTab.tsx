import {
  COST_FUNCTION_LABELS,
  type CostFunction,
  type DirectCostKind,
  type DirectCostLine,
  type FixedCostLine,
  type OperatingPlan,
} from "../../api/model";
import { MonthlySeries } from "../../components/MonthlySeries";
import { Button, CheckField, Hint } from "../../components/ui";

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
      {direct.length === 0 && (
        <p className="muted">Материалы и сдельная оплата — формируют себестоимость продукции (COGS).</p>
      )}
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
          <MonthlySeries n={n} label={d.foreign ? "Сумма (валюта)" : "Сумма"} values={d.amount}
                         onChange={(amount) => updateDirect(i, { amount })} />
          <div className="form-grid" style={{ marginTop: 8 }}>
            <label className="field">
              <span>Отсрочка оплаты, мес.<Hint text="Задержка платежа поставщику — формирует кредиторку (B23)" /></span>
              <input className="input" type="number" min="0" value={d.payment_delay_months}
                     onChange={(e) => updateDirect(i, { payment_delay_months: parseInt(e.target.value || "0", 10) })} />
            </label>
            {d.kind === "materials" && (
              <label className="field">
                <span>Опережающая закупка, мес.<Hint text="Закупка сырья заранее под будущее потребление — формирует запас сырья (B3)" /></span>
                <input className="input" type="number" min="0" value={d.stock_lead_months}
                       onChange={(e) => updateDirect(i, { stock_lead_months: parseInt(e.target.value || "0", 10) })} />
              </label>
            )}
          </div>
          {d.kind === "materials" && (
            <div className="toolbar" style={{ marginTop: 8 }}>
              <CheckField label="Валютный материал (по курсу закупки)" checked={d.foreign ?? false}
                          onChange={(foreign) => updateDirect(i, { foreign })} />
            </div>
          )}
        </div>
      ))}

      <div className="section-head" style={{ marginTop: 22 }}>
        <h2>Постоянные издержки</h2>
        <Button onClick={addFixed}>+ Постоянная издержка</Button>
      </div>
      {fixed.length === 0 && (
        <p className="muted">Аренда, зарплата, реклама и пр. — не зависят от объёма выпуска.</p>
      )}
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
          <MonthlySeries n={n} label={f.foreign ? "Сумма (валюта)" : "Сумма"} values={f.amount}
                         onChange={(amount) => updateFixed(i, { amount })} />
          <div className="form-grid" style={{ marginTop: 8 }}>
            <label className="field">
              <span>Отсрочка оплаты, мес.<Hint text="Задержка платежа — формирует кредиторку (B23)" /></span>
              <input className="input" type="number" min="0" value={f.payment_delay_months}
                     onChange={(e) => updateFixed(i, { payment_delay_months: parseInt(e.target.value || "0", 10) })} />
            </label>
          </div>
          <div className="toolbar" style={{ marginTop: 8, gap: 20 }}>
            <CheckField label="Из прибыли (невычитаемая)" checked={f.from_profit ?? false}
                        onChange={(from_profit) => updateFixed(i, { from_profit })} />
            <CheckField label="Валютная (услуга, по курсу FX)" checked={f.foreign ?? false}
                        onChange={(foreign) => updateFixed(i, { foreign })} />
          </div>
        </div>
      ))}
    </div>
  );
}
