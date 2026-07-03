import type { Company, Environment, StartingBalance } from "../../api/model";
import { EField } from "../../components/EditorField";
import { MonthlyGrid } from "../../components/MonthlyGrid";
import { fmtMoney } from "../../format";

interface Props {
  n: number;
  environment: Environment;
  company: Company;
  onEnvironment: (e: Environment) => void;
  onCompany: (c: Company) => void;
}

const num = (v: string | undefined) => {
  const x = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
};

/** Поля актива/пассива: [ключ, подпись, цвет сегмента]. */
const ASSET_FIELDS: Array<[keyof StartingBalance, string, string]> = [
  ["cash", "Денежные средства", "var(--primary)"],
  ["fixed_assets_net", "Остаточная стоимость ОС", "var(--info)"],
  ["foreign_monetary", "Валютная позиция", "#5E93FF"],
  ["receivables", "Дебиторская задолженность", "#C77DFF"],
  ["raw_materials", "Запас сырья", "var(--warn)"],
  ["finished_goods", "Запас готовой продукции", "var(--border-strong)"],
];

const LIAB_FIELDS: Array<[keyof StartingBalance, string, string]> = [
  ["payables", "Кредиторская задолженность", "var(--warn)"],
  ["debt", "Долгосрочные займы", "#5E93FF"],
  ["paid_in_capital", "Акционерный капитал", "var(--primary)"],
  ["retained_earnings", "Нераспределённая прибыль", "var(--info)"],
];

/** Вкладка «Валюта и старт» (макет «Этап 10»). */
export function CurrencyTab({ n, environment, company, onEnvironment, onCompany }: Props) {
  const sb = company.starting_balance;
  const setSb = (patch: Partial<StartingBalance>) =>
    onCompany({ ...company, starting_balance: { ...sb, ...patch } });

  const fxOpen = num(environment.fx_open) || 1;
  const fxEmpty = !environment.fx_open && (environment.fx_rate ?? []).every((v) => !v);

  const assetVal = (key: keyof StartingBalance): number =>
    key === "foreign_monetary" ? num(sb[key] as string) * fxOpen : num(sb[key] as string);

  const assets = ASSET_FIELDS.reduce((s, [k]) => s + assetVal(k), 0);
  const liabilities = LIAB_FIELDS.reduce((s, [k]) => s + num(sb[k] as string), 0);
  const delta = Math.round((assets - liabilities) * 100) / 100;
  const balanced = Math.abs(delta) <= 0.01;
  const isEmpty = assets === 0 && liabilities === 0;

  // Наклон коромысла: перевес актива — левая чаша вниз.
  const tilt = balanced ? 0 : delta > 0 ? -6 : 6;

  const segs = (
    fields: Array<[keyof StartingBalance, string, string]>,
    total: number,
    val: (k: keyof StartingBalance) => number,
  ) =>
    fields
      .map(([k, label, color]) => ({ label, color, v: val(k) }))
      .filter((s) => s.v > 0)
      .map((s, i) => (
        <div
          key={i}
          className="sb-bar__seg"
          style={{ width: `${(s.v / (total || 1)) * 100}%`, background: s.color }}
          title={`${s.label}: ${fmtMoney(s.v)}`}
        />
      ));

  return (
    <div className="editor-col" style={{ maxWidth: "none" }}>
      <div className="esec">
        <div className="esec__head">
          <div className="esec__num">1</div>
          <div style={{ minWidth: 0 }}>
            <div className="esec__title">Вторая валюта</div>
            <div className="esec__desc">
              Курс для экспортных продаж, валютных статей и валютной позиции.
            </div>
          </div>
        </div>
        <div className="esec__grid" style={{ marginBottom: 14 }}>
          <EField
            label="Стартовый курс"
            suffix="₽ / $"
            note={fxEmpty ? "Пусто — одна валюта (без переоценки)" : undefined}
            value={environment.fx_open ?? ""}
            onChange={(v) => onEnvironment({ ...environment, fx_open: v })}
          />
        </div>
        <MonthlyGrid
          n={n}
          rows={[
            {
              key: "fx",
              title: "Курс, ₽/$",
              values: environment.fx_rate ?? [],
              onChange: (fx_rate) => onEnvironment({ ...environment, fx_rate }),
              agg: "avg",
              unit: "₽/$",
            },
          ]}
        />
      </div>

      <div className="esec">
        <div className="esec__head">
          <div className="esec__num">2</div>
          <div style={{ minWidth: 0 }}>
            <div className="esec__title">Стартовый баланс (действующее предприятие)</div>
            <div className="esec__desc">
              Активы, обязательства и капитал на дату старта. Актив обязан равняться пассиву.
            </div>
          </div>
        </div>

        {!isEmpty && (
          <div className={"sb-verdict" + (balanced ? "" : " sb-verdict--bad")}>
            <div className="sb-scale" aria-hidden="true">
              <span className="sb-scale__base" />
              <span className="sb-scale__post" />
              <span className="sb-scale__beam" style={{ transform: `rotate(${tilt}deg)` }}>
                <span className="sb-scale__pan sb-scale__pan--l" />
                <span className="sb-scale__pan sb-scale__pan--r" />
              </span>
            </div>
            <div style={{ minWidth: 0 }}>
              <div className="sb-verdict__badge">
                {balanced ? "✓ Баланс сходится" : "✗ Баланс расходится"}
              </div>
              <div className="sb-verdict__meta">
                {balanced
                  ? `Актив = Пассив = ${fmtMoney(assets)}`
                  : `Актив − Пассив = ${fmtMoney(delta)} · расчёт вернёт ошибку`}
              </div>
            </div>
          </div>
        )}

        {!isEmpty && (
          <div className="sb-bars">
            <div>
              <div className="sb-bar__head">
                <span className="sb-bar__label">Актив</span>
                <span className="sb-bar__total">{fmtMoney(assets)}</span>
              </div>
              <div className="sb-bar__track">{segs(ASSET_FIELDS, assets, assetVal)}</div>
            </div>
            <div>
              <div className="sb-bar__head">
                <span className="sb-bar__label">Пассив</span>
                <span className="sb-bar__total">{fmtMoney(liabilities)}</span>
              </div>
              <div className="sb-bar__track">
                {segs(LIAB_FIELDS, liabilities, (k) => num(sb[k] as string))}
              </div>
            </div>
          </div>
        )}

        <div className="sb-cols">
          <div>
            <div className="sb-col__head">Активы</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {ASSET_FIELDS.map(([key, label, color]) => (
                <EField
                  key={key}
                  label={label}
                  prefix={key === "foreign_monetary" ? "$" : "₽"}
                  labelRight={<span className="dot-label" style={{ background: color }} />}
                  note={
                    key === "foreign_monetary" && num(sb[key] as string) > 0
                      ? `≈ ${fmtMoney(num(sb[key] as string) * fxOpen)} по стартовому курсу`
                      : undefined
                  }
                  value={(sb[key] as string) ?? "0"}
                  onChange={(v) => setSb({ [key]: v })}
                />
              ))}
            </div>
          </div>
          <div>
            <div className="sb-col__head">Пассивы</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {LIAB_FIELDS.map(([key, label, color]) => (
                <EField
                  key={key}
                  label={label}
                  prefix="₽"
                  labelRight={<span className="dot-label" style={{ background: color }} />}
                  value={(sb[key] as string) ?? "0"}
                  onChange={(v) => setSb({ [key]: v })}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
