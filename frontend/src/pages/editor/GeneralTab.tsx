import type { ProjectHeader, ProjectSettings } from "../../api/model";
import { Field, NumberField, SelectField } from "../../components/ui";

interface Props {
  header: ProjectHeader;
  settings: ProjectSettings;
  onHeader: (h: ProjectHeader) => void;
  onSettings: (s: ProjectSettings) => void;
}

export function GeneralTab({ header, settings, onHeader, onSettings }: Props) {
  const set = (patch: Partial<ProjectSettings>) => onSettings({ ...settings, ...patch });

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

      <h2 style={{ marginTop: 20 }}>Дисконтирование</h2>
      <div className="form-grid">
        <NumberField label="Ставка дисконтирования (год)" step="0.01" value={settings.discount_rate_annual}
                     onChange={(v) => set({ discount_rate_annual: v })} />
      </div>

      <h2 style={{ marginTop: 20 }}>Налоги</h2>
      <div className="form-grid">
        <NumberField label="Налог на прибыль" step="0.01" value={settings.profit_tax_rate}
                     onChange={(v) => set({ profit_tax_rate: v })} />
        <NumberField label="Льгота по прибыли (доля)" step="0.01" value={settings.profit_tax_benefit_share ?? "0"}
                     onChange={(v) => set({ profit_tax_benefit_share: v })} />
        <NumberField label="Страховые взносы с ФОТ" step="0.01" value={settings.payroll_contribution_rate ?? "0"}
                     onChange={(v) => set({ payroll_contribution_rate: v })} />
        <NumberField label="Налог на имущество (год)" step="0.001" value={settings.property_tax_rate}
                     onChange={(v) => set({ property_tax_rate: v })} />
      </div>

      <h2 style={{ marginTop: 20 }}>НДС и запасы</h2>
      <div className="form-grid">
        <NumberField label="НДС" step="0.01" value={settings.vat_rate}
                     onChange={(v) => set({ vat_rate: v })} />
        <SelectField label="Признание НДС" value={settings.vat_basis ?? "shipment"}
                     onChange={(v) => set({ vat_basis: v as ProjectSettings["vat_basis"] })}
                     options={[["shipment", "По отгрузке"], ["payment", "По оплате"]]} />
        <SelectField label="Оценка запасов ГП" value={settings.inventory_method ?? "average"}
                     onChange={(v) => set({ inventory_method: v as ProjectSettings["inventory_method"] })}
                     options={[["average", "Средняя"], ["fifo", "ФИФО"]]} />
        <NumberField label="Производственный цикл (мес.)" step="1"
                     value={settings.production_cycle_months ?? 0}
                     onChange={(v) => set({ production_cycle_months: parseInt(v || "0", 10) || 0 })} />
      </div>

      <h2 style={{ marginTop: 20 }}>Инфляция (год)</h2>
      <div className="form-grid">
        <NumberField label="Цены сбыта" step="0.01" value={settings.inflation_sales ?? "0"}
                     onChange={(v) => set({ inflation_sales: v })} />
        <NumberField label="Прямые издержки" step="0.01" value={settings.inflation_direct ?? "0"}
                     onChange={(v) => set({ inflation_direct: v })} />
        <NumberField label="Зарплата" step="0.01" value={settings.inflation_wages ?? "0"}
                     onChange={(v) => set({ inflation_wages: v })} />
        <NumberField label="Общие издержки" step="0.01" value={settings.inflation_general ?? "0"}
                     onChange={(v) => set({ inflation_general: v })} />
      </div>
    </div>
  );
}
