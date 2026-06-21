import type { OperatingPlan, Product, SalesLine } from "../../api/model";
import { MonthlySeries } from "../../components/MonthlySeries";
import { Button } from "../../components/ui";

interface Props {
  n: number;
  operating: OperatingPlan;
  onChange: (op: OperatingPlan) => void;
}

const emptyPayment = () => ({ prepayment_share: "0", advance_lead_months: 0, payment_delay_months: 0 });

export function SalesTab({ n, operating, onChange }: Props) {
  const products = operating.products;
  const sales = operating.sales;

  const productName = (id: string) => products.find((p) => p.id === id)?.name ?? "";

  const addProduct = () => {
    const id = crypto.randomUUID();
    const product: Product = { id, name: `Продукт ${products.length + 1}` };
    const line: SalesLine = { product_id: id, volume: [], price: [], payment: emptyPayment() };
    onChange({ ...operating, products: [...products, product], sales: [...sales, line] });
  };

  const removeAt = (i: number) => {
    const line = sales[i];
    onChange({
      ...operating,
      sales: sales.filter((_, k) => k !== i),
      products: products.filter((p) => p.id !== line.product_id),
    });
  };

  const updateLine = (i: number, patch: Partial<SalesLine>) =>
    onChange({ ...operating, sales: sales.map((s, k) => (k === i ? { ...s, ...patch } : s)) });

  const updateName = (id: string, name: string) =>
    onChange({ ...operating, products: products.map((p) => (p.id === id ? { ...p, name } : p)) });

  return (
    <div>
      <div className="section-head">
        <h2>План сбыта</h2>
        <Button onClick={addProduct}>+ Продукт</Button>
      </div>
      {sales.length === 0 && <p className="muted">Добавьте продукт.</p>}
      {sales.map((line, i) => (
        <div className="row-card" key={line.product_id}>
          <div className="row-head">
            <input className="input grow" value={productName(line.product_id)}
                   onChange={(e) => updateName(line.product_id, e.target.value)} />
            <Button variant="ghost" onClick={() => removeAt(i)}>Удалить</Button>
          </div>
          <MonthlySeries n={n} label="Объём" values={line.volume}
                         onChange={(volume) => updateLine(i, { volume })} />
          <MonthlySeries n={n} label="Цена" values={line.price}
                         onChange={(price) => updateLine(i, { price })} />
          <div className="form-grid" style={{ marginTop: 10 }}>
            <label className="field">
              <span>Предоплата (доля)</span>
              <input className="input" type="number" step="0.05" value={line.payment.prepayment_share}
                     onChange={(e) => updateLine(i, { payment: { ...line.payment, prepayment_share: e.target.value } })} />
            </label>
            <label className="field">
              <span>Опережение предоплаты, мес.</span>
              <input className="input" type="number" value={line.payment.advance_lead_months}
                     onChange={(e) => updateLine(i, { payment: { ...line.payment, advance_lead_months: parseInt(e.target.value || "0", 10) } })} />
            </label>
            <label className="field">
              <span>Отсрочка оплаты, мес.</span>
              <input className="input" type="number" value={line.payment.payment_delay_months}
                     onChange={(e) => updateLine(i, { payment: { ...line.payment, payment_delay_months: parseInt(e.target.value || "0", 10) } })} />
            </label>
          </div>
        </div>
      ))}
    </div>
  );
}
