import type { OperatingPlan, Product, SalesLine } from "../../api/model";
import { EField } from "../../components/EditorField";
import { IconCart, IconTrash } from "../../components/icons";
import { MonthlyGrid } from "../../components/MonthlyGrid";
import type { MonthlyRow } from "../../components/MonthlyGrid";
import { Button, Switch } from "../../components/ui";

interface Props {
  n: number;
  operating: OperatingPlan;
  onChange: (op: OperatingPlan) => void;
}

const emptyPayment = () => ({ prepayment_share: "0", advance_lead_months: 0, payment_delay_months: 0 });

const num = (v: string | undefined): number => {
  const x = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
};

const inRange01 = (v: string): boolean => {
  const x = Number(v);
  return Number.isFinite(x) && x >= 0 && x <= 1;
};

/** Вкладка «Сбыт» (макет «Этап 6»): карточки продуктов с помесячной сеткой. */
export function SalesTab({ n, operating, onChange }: Props) {
  const { products, sales, production } = operating;

  const productName = (id: string) => products.find((p) => p.id === id)?.name ?? "";
  const productionLine = (id: string) => production.find((l) => l.product_id === id);

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
      production: production.filter((l) => l.product_id !== line.product_id),
    });
  };

  const updateLine = (i: number, patch: Partial<SalesLine>) =>
    onChange({ ...operating, sales: sales.map((s, k) => (k === i ? { ...s, ...patch } : s)) });

  const updateName = (id: string, name: string) =>
    onChange({ ...operating, products: products.map((p) => (p.id === id ? { ...p, name } : p)) });

  /** C2: тумблер «Производство отличается от продаж» — своя строка объёма выпуска. */
  const toggleProduction = (line: SalesLine, on: boolean) => {
    if (on) {
      onChange({
        ...operating,
        production: [...production, { product_id: line.product_id, volume: [...line.volume] }],
      });
    } else {
      onChange({ ...operating, production: production.filter((l) => l.product_id !== line.product_id) });
    }
  };

  const updateProduction = (id: string, volume: string[]) =>
    onChange({
      ...operating,
      production: production.map((l) => (l.product_id === id ? { ...l, volume } : l)),
    });

  return (
    <div>
      <div className="tab-head">
        <div style={{ minWidth: 0 }}>
          <div className="tab-head__title">Сбыт — продукты и план продаж</div>
          <div className="tab-head__sub">
            Объём и цена по месяцам формируют выручку проекта. Горизонт: {n} мес.
          </div>
        </div>
        <Button onClick={addProduct}>＋&nbsp;&nbsp;Продукт</Button>
      </div>

      {sales.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__ico">
            <IconCart size={30} />
          </div>
          <div className="tab-empty__title">Пока нет ни одного продукта</div>
          <div className="tab-empty__sub">
            Добавьте продукт или услугу — объём и цена по месяцам сформируют выручку. Можно
            вставить ряд прямо из Excel.
          </div>
          <Button onClick={addProduct}>＋&nbsp;&nbsp;Добавить первый продукт</Button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {sales.map((line, i) => {
            const cur = line.foreign ? "$" : "₽";
            const prod = productionLine(line.product_id);
            const prepayErr = !inRange01(line.payment.prepayment_share) ? "Доля должна быть от 0 до 1" : "";

            const rows: MonthlyRow[] = [
              {
                key: `vol-${line.product_id}`,
                title: "Объём, шт.",
                values: line.volume,
                onChange: (volume) => updateLine(i, { volume }),
              },
              {
                key: `price-${line.product_id}`,
                title: line.foreign ? "Цена, $ (USD)" : "Цена, ₽",
                values: line.price,
                onChange: (price) => updateLine(i, { price }),
                agg: "avg",
                unit: cur,
              },
              ...(prod
                ? [
                    {
                      key: `prod-${line.product_id}`,
                      title: "Производство, ед.",
                      values: prod.volume,
                      onChange: (volume: string[]) => updateProduction(line.product_id, volume),
                    },
                  ]
                : []),
              {
                key: `rev-${line.product_id}`,
                title: "Выручка",
                compute: (m) => num(line.volume[m]) * num(line.price[m]),
                unit: cur,
              },
            ];

            return (
              <div className="line-card" key={line.product_id}>
                <div className="line-card__head">
                  <div className="line-card__idx">{i + 1}</div>
                  <div className="line-card__name">
                    <input
                      value={productName(line.product_id)}
                      placeholder="Название продукта или услуги"
                      onChange={(e) => updateName(line.product_id, e.target.value)}
                    />
                  </div>
                  {line.foreign && <span className="fx-chip">валюта · по курсу FX</span>}
                  <button
                    type="button"
                    className="line-card__del"
                    title="Удалить продукт"
                    onClick={() => removeAt(i)}
                  >
                    <IconTrash size={16} />
                  </button>
                </div>

                <MonthlyGrid n={n} rows={rows} />

                <label className={"opt-row" + (line.foreign ? " opt-row--on" : "")}>
                  <input
                    type="checkbox"
                    style={{ position: "absolute", opacity: 0, width: 0, height: 0 }}
                    checked={line.foreign ?? false}
                    onChange={(e) => updateLine(i, { foreign: e.target.checked })}
                  />
                  <span className="opt-row__box">{line.foreign ? "✓" : ""}</span>
                  <span style={{ minWidth: 0 }}>
                    <span className="opt-row__label">Экспорт (во 2-й валюте, без НДС, по курсу FX)</span>
                    <span className="opt-row__help">
                      Цена задаётся в валюте; пересчёт в ₽ по курсу на дату отгрузки.
                    </span>
                  </span>
                </label>

                <div style={{ marginTop: 14 }}>
                  <Switch
                    label="Производство отличается от продаж"
                    checked={!!prod}
                    onChange={(on) => toggleProduction(line, on)}
                  />
                </div>

                <div className="terms-head">Условия оплаты</div>
                <div className="terms-grid">
                  <EField
                    label="Предоплата"
                    suffix="доля"
                    hint="Доля 0–1 — формирует «авансы полученные» в пассиве"
                    error={prepayErr}
                    note="→ Авансы полученные"
                    value={line.payment.prepayment_share}
                    onChange={(v) =>
                      updateLine(i, { payment: { ...line.payment, prepayment_share: v } })
                    }
                  />
                  <EField
                    label="Опережение предоплаты"
                    suffix="мес."
                    hint="За сколько месяцев до отгрузки поступает аванс"
                    value={line.payment.advance_lead_months}
                    onChange={(v) =>
                      updateLine(i, {
                        payment: { ...line.payment, advance_lead_months: parseInt(v || "0", 10) || 0 },
                      })
                    }
                  />
                  <EField
                    label="Отсрочка оплаты"
                    suffix="мес."
                    hint="Задержка оплаты после отгрузки — формирует дебиторскую задолженность"
                    note="→ Дебиторская задолженность"
                    value={line.payment.payment_delay_months}
                    onChange={(v) =>
                      updateLine(i, {
                        payment: { ...line.payment, payment_delay_months: parseInt(v || "0", 10) || 0 },
                      })
                    }
                  />
                </div>
              </div>
            );
          })}

          <button type="button" className="add-row" onClick={addProduct}>
            ＋&nbsp;&nbsp;Добавить ещё продукт
          </button>
        </div>
      )}
    </div>
  );
}
