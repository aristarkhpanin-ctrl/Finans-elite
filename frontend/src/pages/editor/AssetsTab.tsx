import type { Asset, AssetCategory, InvestmentPlan } from "../../api/model";
import { EField, ESelect } from "../../components/EditorField";
import { IconBriefcase, IconBuilding, IconLand, IconSettings, IconTrash } from "../../components/icons";
import { Button } from "../../components/ui";
import { fmtMoney } from "../../format";

interface Props {
  investment: InvestmentPlan;
  onChange: (iv: InvestmentPlan) => void;
}

const num = (v: string | number | undefined | null): number => {
  const x = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
};

const CATEGORY_META: Record<AssetCategory, { label: string; icon: JSX.Element }> = {
  equipment: { label: "Оборудование", icon: <IconSettings size={17} /> },
  buildings: { label: "Здания", icon: <IconBuilding size={17} /> },
  land: { label: "Земля", icon: <IconLand size={17} /> },
};

/** Остаточная стоимость на месяц продажи (линейная амортизация; земля не амортизируется). */
function residualAt(a: Asset, month: number): number {
  const cost = num(a.cost);
  if ((a.category ?? "equipment") === "land" || a.life_months <= 0) return cost;
  const used = Math.max(0, month - a.purchase_month);
  const dep = (cost / a.life_months) * Math.min(used, a.life_months);
  return Math.max(0, cost - dep);
}

/** Вкладка «Инвестиции» (макет «Этап 8»): сводка + карточки активов. */
export function AssetsTab({ investment, onChange }: Props) {
  const assets = investment.assets;

  const add = () =>
    onChange({
      assets: [...assets, { name: "Актив", cost: "0", purchase_month: 0, life_months: 12, category: "equipment" }],
    });
  const upd = (i: number, patch: Partial<Asset>) =>
    onChange({ assets: assets.map((a, k) => (k === i ? { ...a, ...patch } : a)) });
  const rm = (i: number) => onChange({ assets: assets.filter((_, k) => k !== i) });

  const totalCapex = assets.reduce((s, a) => s + num(a.cost), 0);
  const saleCount = assets.filter((a) => a.sale_month != null).length;

  return (
    <div>
      <div className="tab-head">
        <div style={{ minWidth: 0 }}>
          <div className="tab-head__title">Инвестиции — основные средства</div>
          <div className="tab-head__sub">
            Капвложения, амортизация, продажа и переоценка активов.
          </div>
        </div>
        <Button onClick={add}>＋&nbsp;&nbsp;Актив</Button>
      </div>

      {assets.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__ico">
            <IconBriefcase size={30} />
          </div>
          <div className="tab-empty__title">Нет основных средств</div>
          <div className="tab-empty__sub">
            Основные средства: капвложения, амортизация, продажа и переоценка. Добавьте
            оборудование, здания или землю.
          </div>
          <Button onClick={add}>＋&nbsp;&nbsp;Добавить первый актив</Button>
        </div>
      ) : (
        <>
          <div className="sum-row">
            <div className="sum-card">
              <div className="sum-card__label">Всего капвложений</div>
              <div className="sum-card__value">{fmtMoney(totalCapex)}</div>
            </div>
            <div className="sum-card">
              <div className="sum-card__label">Активов</div>
              <div className="sum-card__value">{assets.length}</div>
            </div>
            <div className="sum-card">
              <div className="sum-card__label">С продажей</div>
              <div className="sum-card__value">{saleCount}</div>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {assets.map((a, i) => {
              const cat = a.category ?? "equipment";
              const meta = CATEGORY_META[cat];
              const isLand = cat === "land";
              const dep = !isLand && a.life_months > 0 ? num(a.cost) / a.life_months : 0;
              const saleOn = a.sale_month != null;
              const revOn = a.revaluation_month != null;
              const saleErr =
                saleOn && a.sale_month! < a.purchase_month
                  ? "Месяц продажи не может быть раньше покупки"
                  : "";
              const gain = saleOn ? num(a.sale_price) - residualAt(a, a.sale_month!) : 0;

              return (
                <div className="line-card" key={i}>
                  <div className="line-card__head">
                    <div className="line-card__idx" title={meta.label}>
                      {meta.icon}
                    </div>
                    <div className="line-card__name">
                      <input
                        value={a.name}
                        placeholder="Название актива"
                        onChange={(e) => upd(i, { name: e.target.value })}
                      />
                    </div>
                    <span className="prop-chip">{meta.label}</span>
                    {saleOn && <span className="prop-chip prop-chip--cur">Продажа</span>}
                    {revOn && <span className="prop-chip prop-chip--profit">Переоценка</span>}
                    <button type="button" className="line-card__del" title="Удалить актив" onClick={() => rm(i)}>
                      <IconTrash size={16} />
                    </button>
                  </div>

                  <div className="afields-grid">
                    <EField
                      label="Стоимость"
                      prefix="₽"
                      value={a.cost}
                      onChange={(v) => upd(i, { cost: v })}
                    />
                    <EField
                      label="Месяц приобретения"
                      prefix="М"
                      value={a.purchase_month}
                      onChange={(v) => upd(i, { purchase_month: parseInt(v || "0", 10) || 0 })}
                    />
                    <EField
                      label="Срок службы"
                      suffix="мес."
                      labelRight={isLand ? <span className="na-badge">без аморт.</span> : undefined}
                      disabled={isLand}
                      note={
                        isLand
                          ? "Земля не амортизируется"
                          : dep > 0
                            ? `Амортизация ≈ ${fmtMoney(dep)}/мес`
                            : undefined
                      }
                      value={a.life_months}
                      onChange={(v) => upd(i, { life_months: parseInt(v || "0", 10) || 0 })}
                    />
                    <ESelect
                      label="Группа ОС"
                      value={cat}
                      onChange={(v) => upd(i, { category: v as AssetCategory })}
                      options={[
                        ["equipment", "Оборудование"],
                        ["buildings", "Здания"],
                        ["land", "Земля"],
                      ]}
                    />
                  </div>

                  <div className="opt-toggle-row">
                    <button
                      type="button"
                      className={"opt-toggle" + (saleOn ? " opt-toggle--on" : "")}
                      onClick={() =>
                        upd(
                          i,
                          saleOn
                            ? { sale_month: null }
                            : { sale_month: a.purchase_month + 1, sale_price: a.sale_price ?? "0" },
                        )
                      }
                    >
                      <span className="opt-toggle__dot" />
                      Продаётся в течение проекта
                    </button>
                    <button
                      type="button"
                      className={"opt-toggle" + (revOn ? " opt-toggle--on" : "")}
                      onClick={() =>
                        upd(
                          i,
                          revOn
                            ? { revaluation_month: null }
                            : {
                                revaluation_month: a.purchase_month + 1,
                                revaluation_amount: a.revaluation_amount ?? "0",
                              },
                        )
                      }
                    >
                      <span className="opt-toggle__dot" />
                      Переоценка
                    </button>
                  </div>

                  {saleOn && (
                    <div className="expand-block">
                      <div className="expand-block__head">
                        <span>↗</span>Продажа актива
                      </div>
                      <div className="expand-block__grid">
                        <EField
                          label="Месяц продажи"
                          prefix="М"
                          error={saleErr}
                          value={a.sale_month!}
                          onChange={(v) => upd(i, { sale_month: parseInt(v || "0", 10) || 0 })}
                        />
                        <EField
                          label="Цена продажи"
                          prefix="₽"
                          value={a.sale_price ?? "0"}
                          onChange={(v) => upd(i, { sale_price: v })}
                        />
                      </div>
                      {!saleErr && num(a.sale_price) > 0 && (
                        <div
                          className={"gain-note " + (gain >= 0 ? "gain-note--good" : "gain-note--bad")}
                          style={{ marginTop: 10 }}
                        >
                          {gain >= 0 ? "Прибыль" : "Убыток"} от продажи ≈ {fmtMoney(Math.abs(gain))}
                        </div>
                      )}
                    </div>
                  )}

                  {revOn && (
                    <div className="expand-block">
                      <div className="expand-block__head">
                        <span>⟳</span>Переоценка актива
                      </div>
                      <div className="expand-block__grid">
                        <EField
                          label="Месяц переоценки"
                          prefix="М"
                          value={a.revaluation_month!}
                          onChange={(v) => upd(i, { revaluation_month: parseInt(v || "0", 10) || 0 })}
                        />
                        <EField
                          label="Сумма дооценки (±)"
                          prefix="₽"
                          hint="Положительная — дооценка (остаточная стоимость и добавочный капитал растут), отрицательная — уценка"
                          value={a.revaluation_amount ?? "0"}
                          onChange={(v) => upd(i, { revaluation_amount: v })}
                        />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            <button type="button" className="add-row" onClick={add}>
              ＋&nbsp;&nbsp;Добавить ещё актив
            </button>
          </div>
        </>
      )}
    </div>
  );
}
