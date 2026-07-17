import { useRef, useState } from "react";
import type { BomLine, Material, OperatingPlan, Product, SalesLine } from "../../api/model";
import { EField, ESelect } from "../../components/EditorField";
import { IconCart, IconTrash } from "../../components/icons";
import { MonthlyGrid } from "../../components/MonthlyGrid";
import type { MonthlyRow } from "../../components/MonthlyGrid";
import { Button, Switch } from "../../components/ui";
import { fmtMoney } from "../../format";
import { downloadSalesTemplate, parseSalesXlsx } from "../../salesXlsx";

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

  // Импорт/шаблон рядов продаж из Excel (gap 5.3): round-trip через XLSX-грид продукт × месяц.
  const fileRef = useRef<HTMLInputElement>(null);
  const [importMsg, setImportMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const onImportFile = async (file: File) => {
    setImportMsg(null);
    try {
      const res = await parseSalesXlsx(file, operating, n);
      if (res.matched > 0) onChange(res.operating);
      const parts = [`обновлено рядов: ${res.matched}`];
      if (res.skipped.length) parts.push(`не найдены: ${res.skipped.join(", ")}`);
      if (res.ignored) parts.push(`пропущено строк: ${res.ignored}`);
      setImportMsg({ ok: res.matched > 0, text: parts.join(" · ") });
    } catch {
      setImportMsg({ ok: false, text: "Не удалось прочитать файл — нужен XLSX по шаблону." });
    }
  };

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

  // --- Материалы и рецептуры (пер-продуктная себестоимость) ---
  const materials = operating.materials ?? [];
  const setMaterials = (m: Material[]) => onChange({ ...operating, materials: m });
  const addMaterial = () =>
    setMaterials([...materials, { id: crypto.randomUUID(), name: "Материал", unit_price: "0" }]);
  const updMaterial = (i: number, patch: Partial<Material>) =>
    setMaterials(materials.map((m, k) => (k === i ? { ...m, ...patch } : m)));
  const rmMaterial = (i: number) => setMaterials(materials.filter((_, k) => k !== i));
  const updProduct = (id: string, patch: Partial<Product>) =>
    onChange({ ...operating, products: products.map((p) => (p.id === id ? { ...p, ...patch } : p)) });

  return (
    <div>
      <div className="tab-head">
        <div style={{ minWidth: 0 }}>
          <div className="tab-head__title">Сбыт — продукты и план продаж</div>
          <div className="tab-head__sub">
            Объём и цена по месяцам формируют выручку проекта. Горизонт: {n} мес.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {sales.length > 0 && (
            <>
              <Button variant="ghost" onClick={() => downloadSalesTemplate("Продажи-шаблон.xlsx", operating, n)}>
                ⭳&nbsp;&nbsp;Шаблон XLSX
              </Button>
              <Button variant="ghost" onClick={() => fileRef.current?.click()}>
                ⭱&nbsp;&nbsp;Импорт XLSX
              </Button>
            </>
          )}
          <Button onClick={addProduct}>＋&nbsp;&nbsp;Продукт</Button>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void onImportFile(f);
            e.target.value = ""; // разрешить повторный выбор того же файла
          }}
        />
      </div>

      {importMsg && (
        <div className={"field-note" + (importMsg.ok ? "" : " field-note--warn")}
             style={{ margin: "0 0 12px" }}>
          Импорт из Excel: {importMsg.text}
        </div>
      )}

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

                {!line.foreign && (
                  <div style={{ marginTop: 12, maxWidth: 250 }}>
                    <ESelect
                      label="Ставка НДС строки"
                      hint="Льготная категория (напр. продукты питания 10%); «Глобальная» — из настроек проекта"
                      value={line.vat_rate ?? ""}
                      onChange={(v) => updateLine(i, { vat_rate: v || null })}
                      options={[["", "Глобальная"], ["0.20", "20%"], ["0.10", "10%"], ["0", "0% (без НДС)"]]}
                    />
                  </div>
                )}

                <div className="terms-head">Условия оплаты</div>
                <div style={{ margin: "6px 0 10px" }}>
                  <Switch
                    label="Сложная схема (график долей со сдвигами)"
                    checked={(line.payment.schedule?.length ?? 0) > 0}
                    onChange={(on) =>
                      updateLine(i, {
                        payment: {
                          ...line.payment,
                          schedule: on ? [{ offset_months: -1, share: "0.3" },
                                          { offset_months: 0, share: "0.7" }] : [],
                        },
                      })
                    }
                  />
                </div>
                {(line.payment.schedule?.length ?? 0) > 0 ? (
                  <ScheduleEditor
                    parts={line.payment.schedule!}
                    onChange={(schedule) => updateLine(i, { payment: { ...line.payment, schedule } })}
                  />
                ) : (
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
                )}

                {(() => {
                  const p = products.find((x) => x.id === line.product_id);
                  return p ? (
                    <BomBlock product={p} materials={materials}
                              avgPrice={line.price.length ? num(line.price[0]) : 0}
                              onChange={(patch) => updProduct(p.id, patch)} />
                  ) : null;
                })()}
              </div>
            );
          })}

          <button type="button" className="add-row" onClick={addProduct}>
            ＋&nbsp;&nbsp;Добавить ещё продукт
          </button>

          {/* Справочник материалов для рецептур */}
          <div className="res-lib">
            <div className="res-lib__head">
              <div className="res-lib__title">Материалы (для рецептур)</div>
              <Button variant="ghost" onClick={addMaterial}>＋&nbsp;&nbsp;Материал</Button>
            </div>
            {materials.length === 0 ? (
              <p className="muted" style={{ fontSize: 12.5, margin: 0 }}>
                Справочник материалов с ценой за единицу и условиями закупки. Рецептура продукта
                (нормы расхода) превратит их в прямые издержки и себестоимость по продукту.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {materials.map((m, i) => (
                  <div className="res-row" key={m.id}>
                    <input className="res-row__name" value={m.name ?? ""} placeholder="Материал"
                           onChange={(e) => updMaterial(i, { name: e.target.value })} />
                    <EField label={m.foreign ? "Цена ед., $" : "Цена ед., ₽"} value={m.unit_price ?? "0"}
                            onChange={(v) => updMaterial(i, { unit_price: v })} />
                    <EField label="Отсрочка" suffix="мес." value={m.payment_delay_months ?? 0}
                            onChange={(v) => updMaterial(i, { payment_delay_months: parseInt(v || "0", 10) || 0 })} />
                    <EField label="Закупка заранее" suffix="мес." value={m.stock_lead_months ?? 0}
                            onChange={(v) => updMaterial(i, { stock_lead_months: parseInt(v || "0", 10) || 0 })} />
                    <label className="mat-imp" title="Импортный материал: цена в валюте, по курсу FX">
                      <input type="checkbox" checked={m.foreign ?? false}
                             onChange={(e) => updMaterial(i, { foreign: e.target.checked })} />
                      импорт
                    </label>
                    <button type="button" className="line-card__del" title="Удалить материал"
                            onClick={() => rmMaterial(i)}>
                      <IconTrash size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** График оплаты: доли выручки со сдвигами (аванс < 0, отгрузка 0, рассрочка > 0). */
function ScheduleEditor({ parts, onChange }: {
  parts: NonNullable<import("../../api/model").PaymentTerms["schedule"]>;
  onChange: (parts: import("../../api/model").PaymentPart[]) => void;
}) {
  const upd = (i: number, patch: Partial<import("../../api/model").PaymentPart>) =>
    onChange(parts.map((p, k) => (k === i ? { ...p, ...patch } : p)));
  const total = parts.reduce((s, p) => s + num(p.share), 0);
  return (
    <div className="expand-block" style={{ marginTop: 0 }}>
      {parts.map((p, i) => (
        <div className="res-assign" key={i}>
          <EField label="Сдвиг от отгрузки" suffix="мес."
                  hint="Отрицательный — предоплата (авансы B24), положительный — рассрочка (дебиторка B2)"
                  value={p.offset_months}
                  onChange={(v) => upd(i, { offset_months: parseInt(v || "0", 10) || 0 })} />
          <EField label="Доля" suffix="0–1" value={p.share}
                  onChange={(v) => upd(i, { share: v })} />
          <button type="button" className="line-card__del"
                  onClick={() => onChange(parts.filter((_, k) => k !== i))}>
            <IconTrash size={15} />
          </button>
        </div>
      ))}
      <button type="button" className="add-row add-row--sm"
              onClick={() => onChange([...parts, { offset_months: 1, share: "0" }])}>
        ＋&nbsp;&nbsp;Доля оплаты
      </button>
      <div className={"field-note" + (Math.abs(total - 1) > 0.001 ? " field-note--warn" : "")}
           style={{ marginTop: 8 }}>
        Σ долей = {total.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}
        {Math.abs(total - 1) > 0.001 && " — остаток будет получен в месяце отгрузки"}
      </div>
    </div>
  );
}

/** Рецептура продукта (BOM): нормы расхода материалов + сдельная ЗП → себестоимость единицы. */
function BomBlock({ product, materials, avgPrice, onChange }: {
  product: Product;
  materials: Material[];
  avgPrice: number;
  onChange: (patch: Partial<Product>) => void;
}) {
  const bom = product.bom ?? [];
  const byId = new Map(materials.map((m) => [m.id, m]));
  const opts: [string, string][] = [["", "—"], ...materials.map((m) => [m.id, m.name || m.id] as [string, string])];
  const upd = (i: number, patch: Partial<BomLine>) =>
    onChange({ bom: bom.map((b, k) => (k === i ? { ...b, ...patch } : b)) });
  const add = () => onChange({ bom: [...bom, { material_id: materials[0]?.id ?? "", qty_per_unit: "0" }] });
  const rm = (i: number) => onChange({ bom: bom.filter((_, k) => k !== i) });

  const unitCost = bom.reduce((s, b) => {
    const m = byId.get(b.material_id);
    return s + (m ? num(b.qty_per_unit) * num(m.unit_price) : 0);
  }, 0) + num(product.piece_wage_per_unit);
  const hasSpec = bom.length > 0 || num(product.piece_wage_per_unit) > 0;

  return (
    <div className="expand-block">
      <div className="expand-block__head"><span>⚙</span>Рецептура (себестоимость единицы)</div>
      {materials.length === 0 && bom.length === 0 && (
        <p className="muted" style={{ fontSize: 12, margin: "0 0 10px" }}>
          Добавьте материалы в справочник ниже, затем задайте нормы расхода на единицу продукта.
        </p>
      )}
      {bom.map((b, i) => (
        <div className="res-assign" key={i}>
          <ESelect label="Материал" value={b.material_id}
                   onChange={(v) => upd(i, { material_id: v })} options={opts} />
          <EField label="Расход на ед." value={b.qty_per_unit ?? "0"}
                  onChange={(v) => upd(i, { qty_per_unit: v })} />
          <button type="button" className="line-card__del" onClick={() => rm(i)}>
            <IconTrash size={15} />
          </button>
        </div>
      ))}
      <div className="res-assign">
        <EField label="Сдельная зарплата на ед." prefix="₽" value={product.piece_wage_per_unit ?? "0"}
                onChange={(v) => onChange({ piece_wage_per_unit: v })} />
        {materials.length > 0 && (
          <button type="button" className="add-row add-row--sm" style={{ alignSelf: "flex-end" }}
                  onClick={add}>
            ＋&nbsp;&nbsp;Материал рецептуры
          </button>
        )}
      </div>
      {hasSpec && (
        <div className={"gain-note " + (avgPrice > 0 && unitCost > avgPrice ? "gain-note--bad" : "gain-note--good")}
             style={{ marginTop: 8 }}>
          Себестоимость ≈ {fmtMoney(unitCost)}/ед. (в базовых ценах)
          {avgPrice > 0 && ` · цена ${fmtMoney(avgPrice)} → маржа ≈ ${fmtMoney(avgPrice - unitCost)}/ед.`}
        </div>
      )}
    </div>
  );
}
