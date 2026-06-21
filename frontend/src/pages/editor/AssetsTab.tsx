import type { Asset, InvestmentPlan } from "../../api/model";
import { Button } from "../../components/ui";

interface Props {
  investment: InvestmentPlan;
  onChange: (iv: InvestmentPlan) => void;
}

export function AssetsTab({ investment, onChange }: Props) {
  const assets = investment.assets;

  const add = () =>
    onChange({ assets: [...assets, { name: "Актив", cost: "0", purchase_month: 0, life_months: 12 }] });
  const upd = (i: number, patch: Partial<Asset>) =>
    onChange({ assets: assets.map((a, k) => (k === i ? { ...a, ...patch } : a)) });
  const rm = (i: number) => onChange({ assets: assets.filter((_, k) => k !== i) });

  return (
    <div>
      <div className="section-head">
        <h2>Инвестиции (активы)</h2>
        <Button onClick={add}>+ Актив</Button>
      </div>
      {assets.length === 0 && <p className="muted">Активы не заданы.</p>}
      {assets.map((a, i) => (
        <div className="row-card" key={i}>
          <div className="row-head">
            <input className="input grow" value={a.name} onChange={(e) => upd(i, { name: e.target.value })} />
            <Button variant="ghost" onClick={() => rm(i)}>Удалить</Button>
          </div>
          <div className="form-grid">
            <label className="field"><span>Стоимость</span>
              <input className="input" type="number" value={a.cost} onChange={(e) => upd(i, { cost: e.target.value })} /></label>
            <label className="field"><span>Месяц приобретения</span>
              <input className="input" type="number" value={a.purchase_month} onChange={(e) => upd(i, { purchase_month: parseInt(e.target.value || "0", 10) })} /></label>
            <label className="field"><span>Срок службы, мес.</span>
              <input className="input" type="number" value={a.life_months} onChange={(e) => upd(i, { life_months: parseInt(e.target.value || "1", 10) })} /></label>
          </div>
        </div>
      ))}
    </div>
  );
}
