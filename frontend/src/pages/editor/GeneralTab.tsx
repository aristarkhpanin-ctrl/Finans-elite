import type { ProjectHeader, ProjectSettings } from "../../api/model";
import { Field, NumberField } from "../../components/ui";

interface Props {
  header: ProjectHeader;
  settings: ProjectSettings;
  onHeader: (h: ProjectHeader) => void;
  onSettings: (s: ProjectSettings) => void;
}

export function GeneralTab({ header, settings, onHeader, onSettings }: Props) {
  return (
    <div>
      <h2>Проект</h2>
      <div className="form-grid">
        <Field label="Название" value={header.name}
               onChange={(e) => onHeader({ ...header, name: e.target.value })} />
        <Field label="Дата старта" type="date" value={header.start_date}
               onChange={(e) => onHeader({ ...header, start_date: e.target.value })} />
        <NumberField label="Длительность, мес." value={header.duration_months}
                     onChange={(v) => onHeader({ ...header, duration_months: Math.max(1, parseInt(v || "1", 10)) })} />
      </div>

      <h2 style={{ marginTop: 20 }}>Настройка расчёта</h2>
      <div className="form-grid">
        <NumberField label="Ставка дисконтирования (год)" step="0.01" value={settings.discount_rate_annual}
                     onChange={(v) => onSettings({ ...settings, discount_rate_annual: v })} />
        <NumberField label="Налог на прибыль" step="0.01" value={settings.profit_tax_rate}
                     onChange={(v) => onSettings({ ...settings, profit_tax_rate: v })} />
        <NumberField label="НДС" step="0.01" value={settings.vat_rate}
                     onChange={(v) => onSettings({ ...settings, vat_rate: v })} />
        <NumberField label="Налог на имущество (год)" step="0.001" value={settings.property_tax_rate}
                     onChange={(v) => onSettings({ ...settings, property_tax_rate: v })} />
      </div>
    </div>
  );
}
