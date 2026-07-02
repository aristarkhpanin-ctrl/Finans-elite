import type { ProjectHeader, ProjectSettings } from "../../api/model";
import { EField, EPercentField, ESelect } from "../../components/EditorField";

interface Props {
  header: ProjectHeader;
  settings: ProjectSettings;
  onHeader: (h: ProjectHeader) => void;
  onSettings: (s: ProjectSettings) => void;
}

function Section({
  num,
  title,
  desc,
  children,
}: {
  num: string;
  title: string;
  desc: string;
  children: React.ReactNode;
}) {
  return (
    <div className="esec">
      <div className="esec__head">
        <div className="esec__num">{num}</div>
        <div style={{ minWidth: 0 }}>
          <div className="esec__title">{title}</div>
          <div className="esec__desc">{desc}</div>
        </div>
      </div>
      <div className="esec__grid">{children}</div>
    </div>
  );
}

const inRange01 = (v: string | undefined | null): boolean => {
  const x = Number(v ?? 0);
  return Number.isFinite(x) && x >= 0 && x <= 1;
};

/** Вкладка «Проект» (макет «Этап 5»): 5 секций-карточек 01–05. */
export function GeneralTab({ header, settings, onHeader, onSettings }: Props) {
  const set = (patch: Partial<ProjectSettings>) => onSettings({ ...settings, ...patch });

  const durationErr = header.duration_months < 1 ? "Минимум 1 месяц" : "";
  const liqErr = !inRange01(settings.liquidation_recovery_rate) ? "Значение должно быть от 0 до 1" : "";
  const benefitErr = !inRange01(settings.profit_tax_benefit_share) ? "Значение должно быть от 0 до 1" : "";

  return (
    <div className="editor-col">
      <Section num="1" title="Проект" desc="Базовые параметры расчётного горизонта">
        <EField
          label="Название проекта"
          text
          full
          placeholder="Напр. «Завод полимерной упаковки»"
          value={header.name}
          onChange={(v) => onHeader({ ...header, name: v })}
        />
        <EField
          label="Дата старта"
          date
          value={header.start_date}
          onChange={(v) => onHeader({ ...header, start_date: v })}
        />
        <EField
          label="Длительность"
          suffix="мес."
          error={durationErr}
          value={header.duration_months}
          onChange={(v) => onHeader({ ...header, duration_months: parseInt(v || "0", 10) || 0 })}
        />
      </Section>

      <Section num="2" title="Дисконтирование и оценка" desc="Параметры NPV и оценки стоимости бизнеса">
        <EPercentField
          label="Ставка дисконтирования"
          suffix="% / год"
          value={settings.discount_rate_annual}
          onChange={(v) => set({ discount_rate_annual: v })}
        />
        <EPercentField
          label="Темп роста для оценки, g"
          suffix="%"
          hint="Должен быть меньше ставки дисконтирования — иначе модель Гордона не считается"
          value={settings.terminal_growth_rate ?? "0"}
          onChange={(v) => set({ terminal_growth_rate: v })}
        />
        <EField
          label="Мультипликатор прибыли"
          suffix="×"
          hint="0 — оценка по мультипликатору выключена"
          value={settings.valuation_earnings_multiple ?? "0"}
          onChange={(v) => set({ valuation_earnings_multiple: v })}
        />
        <EField
          label="Доля возврата при ликвидации"
          suffix="доля"
          hint="От 0 до 1: какая часть активов возвращается при ликвидации"
          error={liqErr}
          value={settings.liquidation_recovery_rate ?? "0"}
          onChange={(v) => set({ liquidation_recovery_rate: v })}
        />
      </Section>

      <Section num="3" title="Налоги" desc="Ставки и льготы налогообложения">
        <EPercentField
          label="Налог на прибыль"
          suffix="%"
          value={settings.profit_tax_rate}
          onChange={(v) => set({ profit_tax_rate: v })}
        />
        <EField
          label="Льгота по прибыли"
          suffix="доля"
          hint="Доля прибыли 0–1, освобождённая от налога"
          error={benefitErr}
          value={settings.profit_tax_benefit_share ?? "0"}
          onChange={(v) => set({ profit_tax_benefit_share: v })}
        />
        <EPercentField
          label="Страховые взносы с ФОТ"
          suffix="%"
          value={settings.payroll_contribution_rate ?? "0"}
          onChange={(v) => set({ payroll_contribution_rate: v })}
        />
        <EPercentField
          label="Налог на имущество"
          suffix="% / год"
          value={settings.property_tax_rate}
          onChange={(v) => set({ property_tax_rate: v })}
        />
        <EPercentField
          label="Налог с продаж"
          suffix="%"
          value={settings.sales_tax_rate ?? "0"}
          onChange={(v) => set({ sales_tax_rate: v })}
        />
      </Section>

      <Section num="4" title="НДС и запасы" desc="Учётная политика по НДС и складу">
        <EPercentField
          label="НДС"
          suffix="%"
          value={settings.vat_rate}
          onChange={(v) => set({ vat_rate: v })}
        />
        <ESelect
          label="Признание НДС"
          value={settings.vat_basis ?? "shipment"}
          onChange={(v) => set({ vat_basis: v as ProjectSettings["vat_basis"] })}
          options={[
            ["shipment", "По отгрузке"],
            ["payment", "По оплате"],
          ]}
        />
        <ESelect
          label="Оценка запасов ГП"
          value={settings.inventory_method ?? "average"}
          onChange={(v) => set({ inventory_method: v as ProjectSettings["inventory_method"] })}
          options={[
            ["average", "Средняя"],
            ["fifo", "ФИФО"],
          ]}
        />
        <EField
          label="Производственный цикл"
          suffix="мес."
          hint="Задержка между запуском и выпуском → формирует НЗП"
          value={settings.production_cycle_months ?? 0}
          onChange={(v) => set({ production_cycle_months: parseInt(v || "0", 10) || 0 })}
        />
      </Section>

      <Section num="5" title="Инфляция (год)" desc="Годовые темпы роста по группам">
        <EPercentField
          label="Цены сбыта"
          suffix="%"
          value={settings.inflation_sales ?? "0"}
          onChange={(v) => set({ inflation_sales: v })}
        />
        <EPercentField
          label="Прямые издержки"
          suffix="%"
          value={settings.inflation_direct ?? "0"}
          onChange={(v) => set({ inflation_direct: v })}
        />
        <EPercentField
          label="Зарплата"
          suffix="%"
          value={settings.inflation_wages ?? "0"}
          onChange={(v) => set({ inflation_wages: v })}
        />
        <EPercentField
          label="Общие издержки"
          suffix="%"
          value={settings.inflation_general ?? "0"}
          onChange={(v) => set({ inflation_general: v })}
        />
      </Section>
    </div>
  );
}
