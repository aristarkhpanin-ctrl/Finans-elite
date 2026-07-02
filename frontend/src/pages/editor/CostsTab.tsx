import {
  COST_FUNCTION_LABELS,
  type CostFunction,
  type DirectCostKind,
  type DirectCostLine,
  type FixedCostLine,
  type OperatingPlan,
} from "../../api/model";
import { EField, ESelect } from "../../components/EditorField";
import { IconBox, IconTrash } from "../../components/icons";
import { MonthlyGrid } from "../../components/MonthlyGrid";
import { Button, CountChip, Switch } from "../../components/ui";

interface Props {
  n: number;
  operating: OperatingPlan;
  onChange: (op: OperatingPlan) => void;
}

/** Вкладка «Издержки» (макет «Этап 7»): прямые и постоянные статьи. */
export function CostsTab({ n, operating, onChange }: Props) {
  const direct = operating.direct_costs;
  const fixed = operating.fixed_costs;

  const addDirect = () =>
    onChange({
      ...operating,
      direct_costs: [
        ...direct,
        { name: "Материалы", kind: "materials", amount: [], payment_delay_months: 0, stock_lead_months: 0 },
      ],
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

  const delayErr = (v: number) => (v < 0 ? "Не может быть отрицательным" : "");

  return (
    <div>
      <div className="tab-head">
        <div style={{ minWidth: 0 }}>
          <div className="tab-head__title">Издержки — прямые и постоянные</div>
          <div className="tab-head__sub">
            Себестоимость и операционные расходы по месяцам. Горизонт: {n} мес.
          </div>
        </div>
      </div>

      {/* ─── Прямые ─── */}
      <div className="csec">
        <div className="csec__head">
          <div style={{ minWidth: 0 }}>
            <div className="csec__titlerow">
              <span className="csec__dot" />
              <span className="csec__title">Прямые издержки</span>
              {direct.length > 0 && <CountChip>{direct.length}</CountChip>}
            </div>
            <div className="csec__desc">
              Материалы и сдельная оплата — формируют себестоимость продукции (COGS).
            </div>
          </div>
          <Button onClick={addDirect}>＋&nbsp;&nbsp;Статья</Button>
        </div>

        {direct.length === 0 ? (
          <div className="tab-empty" style={{ padding: "38px 24px" }}>
            <div className="tab-empty__ico">
              <IconBox size={26} />
            </div>
            <div className="tab-empty__title">Нет прямых издержек</div>
            <div className="tab-empty__sub">
              Материалы и сдельная оплата формируют себестоимость продукции (COGS).
            </div>
            <Button onClick={addDirect}>＋&nbsp;&nbsp;Добавить статью</Button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {direct.map((d, i) => {
              const isMat = d.kind === "materials";
              return (
                <div className="line-card" key={i}>
                  <div className="line-card__head">
                    <div className="line-card__idx">{i + 1}</div>
                    <div className="line-card__name">
                      <input
                        value={d.name}
                        placeholder="Название статьи"
                        onChange={(e) => updateDirect(i, { name: e.target.value })}
                      />
                    </div>
                    <span className="prop-chip">{isMat ? "Материалы" : "Сдельная ЗП"}</span>
                    {d.foreign && <span className="prop-chip prop-chip--cur">Валютный</span>}
                    <button
                      type="button"
                      className="line-card__del"
                      title="Удалить"
                      onClick={() => removeDirect(i)}
                    >
                      <IconTrash size={16} />
                    </button>
                  </div>

                  <MonthlyGrid
                    n={n}
                    rows={[
                      {
                        key: `direct-${i}`,
                        title: d.foreign ? "Затраты, вал./мес" : "Затраты, ₽/мес",
                        values: d.amount,
                        onChange: (amount) => updateDirect(i, { amount }),
                        unit: d.foreign ? "вал." : "₽",
                      },
                    ]}
                  />

                  <div className="terms-head">Параметры статьи</div>
                  <div className="terms-grid">
                    <ESelect
                      label="Тип"
                      value={d.kind}
                      onChange={(v) => updateDirect(i, { kind: v as DirectCostKind })}
                      options={[
                        ["materials", "Материалы"],
                        ["piece_wages", "Сдельная зарплата"],
                      ]}
                    />
                    <EField
                      label="Отсрочка оплаты"
                      suffix="мес."
                      hint="Задержка оплаты поставщику после поставки → формирует кредиторскую задолженность"
                      note="→ Кредиторская задолженность"
                      error={delayErr(d.payment_delay_months)}
                      value={d.payment_delay_months}
                      onChange={(v) => updateDirect(i, { payment_delay_months: parseInt(v || "0", 10) || 0 })}
                    />
                    {isMat && (
                      <EField
                        label="Опережающая закупка"
                        suffix="мес."
                        hint="За сколько месяцев заранее закупается материал → формирует запас сырья"
                        note="→ Запас сырья"
                        value={d.stock_lead_months}
                        onChange={(v) => updateDirect(i, { stock_lead_months: parseInt(v || "0", 10) || 0 })}
                      />
                    )}
                  </div>

                  {isMat && (
                    <div style={{ marginTop: 14 }}>
                      <Switch
                        label="Валютный материал (по курсу закупки)"
                        checked={d.foreign ?? false}
                        onChange={(foreign) => updateDirect(i, { foreign })}
                      />
                    </div>
                  )}
                </div>
              );
            })}
            <button type="button" className="add-row" onClick={addDirect}>
              ＋&nbsp;&nbsp;Добавить ещё статью
            </button>
          </div>
        )}
      </div>

      {/* ─── Постоянные ─── */}
      <div className="csec">
        <div className="csec__head">
          <div style={{ minWidth: 0 }}>
            <div className="csec__titlerow">
              <span className="csec__dot csec__dot--fixed" />
              <span className="csec__title">Постоянные издержки</span>
              {fixed.length > 0 && <CountChip>{fixed.length}</CountChip>}
            </div>
            <div className="csec__desc">Аренда, зарплата, реклама и пр. — не зависят от объёма выпуска.</div>
          </div>
          <Button onClick={addFixed}>＋&nbsp;&nbsp;Статья</Button>
        </div>

        {fixed.length === 0 ? (
          <div className="tab-empty" style={{ padding: "38px 24px" }}>
            <div className="tab-empty__ico">
              <IconBox size={26} />
            </div>
            <div className="tab-empty__title">Нет постоянных издержек</div>
            <div className="tab-empty__sub">Аренда, зарплата, реклама и пр. — не зависят от объёма выпуска.</div>
            <Button onClick={addFixed}>＋&nbsp;&nbsp;Добавить статью</Button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {fixed.map((f, i) => (
              <div className="line-card" key={i}>
                <div className="line-card__head">
                  <div className="line-card__idx line-card__idx--fixed">{i + 1}</div>
                  <div className="line-card__name">
                    <input
                      value={f.name}
                      placeholder="Название статьи"
                      onChange={(e) => updateFixed(i, { name: e.target.value })}
                    />
                  </div>
                  <span className="prop-chip">{COST_FUNCTION_LABELS[f.function]}</span>
                  {f.from_profit && <span className="prop-chip prop-chip--profit">Из прибыли</span>}
                  {f.foreign && <span className="prop-chip prop-chip--cur">Валютная</span>}
                  <button
                    type="button"
                    className="line-card__del"
                    title="Удалить"
                    onClick={() => removeFixed(i)}
                  >
                    <IconTrash size={16} />
                  </button>
                </div>

                <MonthlyGrid
                  n={n}
                  rows={[
                    {
                      key: `fixed-${i}`,
                      title: f.foreign ? "Затраты, вал./мес" : "Затраты, ₽/мес",
                      values: f.amount,
                      onChange: (amount) => updateFixed(i, { amount }),
                      unit: f.foreign ? "вал." : "₽",
                    },
                  ]}
                />

                <div className="terms-head">Параметры статьи</div>
                <div className="terms-grid">
                  <ESelect
                    label="Функция"
                    value={f.function}
                    onChange={(v) => updateFixed(i, { function: v as CostFunction })}
                    options={Object.entries(COST_FUNCTION_LABELS) as [string, string][]}
                  />
                  <EField
                    label="Отсрочка оплаты"
                    suffix="мес."
                    hint="Задержка платежа → формирует кредиторскую задолженность"
                    note="→ Кредиторская задолженность"
                    error={delayErr(f.payment_delay_months)}
                    value={f.payment_delay_months}
                    onChange={(v) => updateFixed(i, { payment_delay_months: parseInt(v || "0", 10) || 0 })}
                  />
                </div>

                <div style={{ marginTop: 14, display: "flex", gap: 22, flexWrap: "wrap" }}>
                  <Switch
                    label="Из прибыли (невычитаемая)"
                    checked={f.from_profit ?? false}
                    onChange={(from_profit) => updateFixed(i, { from_profit })}
                  />
                  <Switch
                    label="Валютная (услуга, по курсу FX)"
                    checked={f.foreign ?? false}
                    onChange={(foreign) => updateFixed(i, { foreign })}
                  />
                </div>
              </div>
            ))}
            <button type="button" className="add-row" onClick={addFixed}>
              ＋&nbsp;&nbsp;Добавить ещё статью
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
