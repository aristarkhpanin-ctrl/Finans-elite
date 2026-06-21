import type { Company, Environment, StartingBalance } from "../../api/model";
import { MonthlySeries } from "../../components/MonthlySeries";
import { NumberField } from "../../components/ui";

interface Props {
  n: number;
  environment: Environment;
  company: Company;
  onEnvironment: (e: Environment) => void;
  onCompany: (c: Company) => void;
}

const num = (v: string | undefined) => Number(v ?? "0") || 0;

export function CurrencyTab({ n, environment, company, onEnvironment, onCompany }: Props) {
  const sb = company.starting_balance;
  const setSb = (patch: Partial<StartingBalance>) =>
    onCompany({ ...company, starting_balance: { ...sb, ...patch } });

  // Стартовый баланс: актив (деньги + ОС + валютная позиция×курс) vs пассив (долг + капитал).
  const fxOpen = num(environment.fx_open) || 1;
  const assets = num(sb.cash) + num(sb.fixed_assets_net) + num(sb.foreign_monetary) * fxOpen;
  const liabilities = num(sb.debt) + num(sb.paid_in_capital) + num(sb.retained_earnings);
  const diff = Math.round((assets - liabilities) * 100) / 100;

  return (
    <div>
      <h2>Вторая валюта</h2>
      <div className="form-grid">
        <NumberField label="Курс на старте (основной за единицу)" step="0.01"
                     value={environment.fx_open ?? "1"}
                     onChange={(v) => onEnvironment({ ...environment, fx_open: v })} />
      </div>
      <MonthlySeries n={n} label="Курс по месяцам (конец периода)" values={environment.fx_rate ?? []}
                     onChange={(fx_rate) => onEnvironment({ ...environment, fx_rate })} />
      <p className="muted" style={{ fontSize: 13 }}>
        Пусто — одна валюта (без переоценки). Курс используют статьи с флагом «валютная/экспорт».
      </p>

      <h2 style={{ marginTop: 22 }}>Стартовый баланс (действующее предприятие)</h2>
      <div className="form-grid">
        <NumberField label="Денежные средства" value={sb.cash ?? "0"}
                     onChange={(v) => setSb({ cash: v })} />
        <NumberField label="Остаточная стоимость ОС" value={sb.fixed_assets_net ?? "0"}
                     onChange={(v) => setSb({ fixed_assets_net: v })} />
        <NumberField label="Валютная позиция (ед. 2-й валюты)" value={sb.foreign_monetary ?? "0"}
                     onChange={(v) => setSb({ foreign_monetary: v })} />
        <NumberField label="Долгосрочные займы" value={sb.debt ?? "0"}
                     onChange={(v) => setSb({ debt: v })} />
        <NumberField label="Акционерный капитал" value={sb.paid_in_capital ?? "0"}
                     onChange={(v) => setSb({ paid_in_capital: v })} />
        <NumberField label="Нераспределённая прибыль" value={sb.retained_earnings ?? "0"}
                     onChange={(v) => setSb({ retained_earnings: v })} />
      </div>
      <p style={{ fontSize: 13, color: diff === 0 ? "var(--success)" : "var(--danger)" }}>
        {diff === 0
          ? "Баланс сходится ✓"
          : `Актив − Пассив = ${diff} (должно быть 0, иначе расчёт не пройдёт)`}
      </p>
    </div>
  );
}
