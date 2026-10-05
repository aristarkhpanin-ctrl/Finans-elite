import type { CustomTax, Environment, ProjectHeader, ProjectSettings } from "../../api/model";
import { EField, EPercentField, ESelect } from "../../components/EditorField";
import { IconTrash } from "../../components/icons";
import { fracToPct, isShare, parseModelNumber, pctToFrac } from "../../format";

type SeriesKey =
  | "inflation_sales_series"
  | "inflation_direct_series"
  | "inflation_wages_series"
  | "inflation_general_series";

const INFL_GROUPS: [SeriesKey, keyof ProjectSettings, string][] = [
  ["inflation_sales_series", "inflation_sales", "Сбыт"],
  ["inflation_direct_series", "inflation_direct", "Прямые"],
  ["inflation_wages_series", "inflation_wages", "Зарплата"],
  ["inflation_general_series", "inflation_general", "Общие"],
];

/** Инфляция по годам (gap 1.9): таблица год × группа переопределяет константы. */
function InflationByYear({
  header,
  settings,
  set,
}: {
  header: ProjectHeader;
  settings: ProjectSettings;
  set: (patch: Partial<ProjectSettings>) => void;
}) {
  const years = Math.max(1, Math.ceil((header.duration_months || 12) / 12));
  const active = INFL_GROUPS.some(([key]) => (settings[key] as string[] | undefined)?.length);

  const enable = () => {
    const patch: Partial<ProjectSettings> = {};
    for (const [key, scalar] of INFL_GROUPS) {
      patch[key] = Array.from({ length: years }, () => (settings[scalar] as string) ?? "0");
    }
    set(patch);
  };
  const disable = () =>
    set({
      inflation_sales_series: [],
      inflation_direct_series: [],
      inflation_wages_series: [],
      inflation_general_series: [],
    });

  const cell = (key: SeriesKey, y: number): string => {
    const arr = (settings[key] as string[] | undefined) ?? [];
    return arr[y] ?? arr[arr.length - 1] ?? "0";
  };
  const updCell = (key: SeriesKey, y: number, frac: string) => {
    const arr = Array.from({ length: years }, (_, i) => cell(key, i));
    arr[y] = frac;
    set({ [key]: arr } as Partial<ProjectSettings>);
  };

  return (
    <div className="infl-year">
      <div className="infl-year__head">
        <div>
          <div className="infl-year__title">Инфляция по годам</div>
          <div className="infl-year__sub">
            Ряд ставок по годам переопределяет константы выше (за пределом ряда держится
            последнее значение).
          </div>
        </div>
        <button type="button" className="opt-toggle" onClick={active ? disable : enable}>
          <span className="opt-toggle__dot" />
          {active ? "Сбросить к константам" : "Задать по годам"}
        </button>
      </div>
      {active && (
        <div className="infl-grid fe-scroll">
          <table>
            <thead>
              <tr>
                <th>Год</th>
                {INFL_GROUPS.map(([key, , label]) => (
                  <th key={key}>{label}, %</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: years }, (_, y) => (
                <tr key={y}>
                  <td className="infl-grid__year">{y + 1}</td>
                  {INFL_GROUPS.map(([key, , groupLabel]) => (
                    <td key={key}>
                      <input
                        inputMode="decimal"
                        aria-label={`Инфляция «${groupLabel}», год ${y + 1}, %`}
                        value={fracToPct(cell(key, y))}
                        onChange={(e) => updCell(key, y, pctToFrac(e.target.value))}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

interface Props {
  header: ProjectHeader;
  settings: ProjectSettings;
  environment: Environment;
  onHeader: (h: ProjectHeader) => void;
  onSettings: (s: ProjectSettings) => void;
  onEnvironment: (e: Environment) => void;
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
        <div className="esec__num" aria-hidden="true">{num}</div>
        <div style={{ minWidth: 0 }}>
          {/* Заголовок секции — h2 (пакет K, K5): диктор ходит по заголовкам, а их на
              вкладке не было ни одного. Номер — оформление. */}
          <h2 className="esec__title">{title}</h2>
          <div className="esec__desc">{desc}</div>
        </div>
      </div>
      <div className="esec__grid">{children}</div>
    </div>
  );
}

const PERIODICITY_OPTIONS: [string, string][] = [
  ["month", "Ежемесячно"],
  ["quarter", "Ежеквартально"],
  ["year", "Ежегодно"],
];

/** Периоды уплаты календарные (с 0.9.46): при старте не в январе первый период неполный. */
// Сроки уплаты — по закону (движок 0.9.51): подсказка говорит, когда деньги уходят, а не
// только как копится период. Периоды календарные; при старте не в январе первый неполный.
const PROFIT_DUE_HINT =
  "Периоды календарные. Уплата — в месяце после периода (до 28-го), налог за год — в " +
  "марте следующего года (ст. 287 НК РФ). Не уплаченное к концу горизонта остаётся " +
  "задолженностью.";
const VAT_DUE_HINT =
  "По закону — квартал: три равные доли в трёх месяцах после него (ст. 174 НК РФ). " +
  "«Ежемесячно» и «ежегодно» — упрощения модели: уплата в месяце после периода.";
// Возмещение излишка (движок 0.9.55): заявляется по итогам квартала — налогового периода
// НДС, — даже при помесячной уплате; «в зачёт» — прежнее поведение, оно тоже законно.
const VAT_REFUND_HINT =
  "Излишек вычетов на конец квартала возмещается после камеральной проверки (ст. 176 НК " +
  "РФ). «В зачёт» — излишек гасит налог следующих периодов (перенос вычетов, п. 1.1 ст. 172).";
const VAT_REFUND_LAG_HINT =
  "Месяцев после конца квартала: декларация — до 25-го числа, проверка — два месяца.";
// Закрытие расчётов конца горизонта (движок 0.9.57): без него неуплаченный налог завышал
// NPV, а неинкассированная дебиторка — занижала; подсказка называет обе стороны.
const RELEASE_HINT =
  "Дебиторка, запасы и НДС к получению приходят деньгами, налоги, кредиторка и полученные " +
  "авансы уходят — в последнем месяце потока для NPV и IRR. Без этого неуплаченный налог " +
  "завышает NPV, а неинкассированная дебиторка — занижает.";
const CUSTOM_DUE_HINT =
  "Периоды календарные; уплата — в месяце, следующем за периодом.";
// Срок взносов (движок 0.9.54) привязан к начислению зарплаты, а не к её выплате: задержка
// выплаты в статье персонала взносы не задерживает — это и сказано рядом со ставкой.
const CONTRIBUTION_DUE_HINT =
  "Начисляются с оплаты труда и уплачиваются в следующем месяце, до 28-го (п. 3 ст. 431 " +
  "НК РФ), — даже если зарплата выплачивается позже.";


/** Настраиваемые налоги (SPEC §22.9): список «база × ставка» поверх профильных ставок. */
function CustomTaxes({ environment, onChange }: { environment: Environment; onChange: (e: Environment) => void }) {
  const taxes = environment.taxes ?? [];
  const setTaxes = (next: CustomTax[]) => onChange({ ...environment, taxes: next });
  const upd = (i: number, patch: Partial<CustomTax>) =>
    setTaxes(taxes.map((t, k) => (k === i ? { ...t, ...patch } : t)));
  const add = () =>
    setTaxes([...taxes, { name: `Налог ${taxes.length + 1}`, rate: "0", base: "revenue",
                          formula: "", periodicity: "month", allocation: "expense" }]);
  const rm = (i: number) => setTaxes(taxes.filter((_, k) => k !== i));

  return (
    <div className="esec">
      <div className="esec__head">
        <div className="esec__num">6</div>
        <div style={{ minWidth: 0 }}>
          <div className="esec__title">Настраиваемые налоги</div>
          <div className="esec__desc">
            Произвольные налоги поверх профильных ставок: база × ставка. Базы считаются по
            показателям до настраиваемых налогов; квартал/год копят задолженность в B21.
          </div>
        </div>
      </div>
      {taxes.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 12 }}>
          {taxes.map((t, i) => (
            <div className="line-card" key={i}>
              <div className="line-card__head">
                <div className="line-card__idx">{i + 1}</div>
                <div className="line-card__name">
                  <input value={t.name} placeholder="Название налога, напр. «Экологический сбор»"
                         onChange={(e) => upd(i, { name: e.target.value })} />
                </div>
                <button type="button" className="line-card__del" title="Удалить налог"
                        onClick={() => rm(i)}>
                  <IconTrash size={16} />
                </button>
              </div>
              <div className="esec__grid">
                <ESelect
                  label="База"
                  value={t.base}
                  onChange={(v) => upd(i, { base: v as CustomTax["base"] })}
                  options={[
                    ["revenue", "Выручка (I1)"],
                    ["payroll", "ФОТ (I6+I13..I15)"],
                    ["property", "Имущество (B13+B14)"],
                    ["profit", "Прибыль (I26, нарастающим итогом года)"],
                    ["formula", "Формула…"],
                  ]}
                />
                <EPercentField
                  label="Ставка"
                  suffix="%"
                  value={t.rate}
                  onChange={(v) => upd(i, { rate: v })}
                />
                <ESelect
                  label="Периодичность уплаты"
                  hint={CUSTOM_DUE_HINT}
                  value={t.periodicity}
                  onChange={(v) => upd(i, { periodicity: v as CustomTax["periodicity"] })}
                  options={[
                    ["month", "Ежемесячно"],
                    ["quarter", "Ежеквартально"],
                    ["year", "Ежегодно"],
                  ]}
                />
                <ESelect
                  label="Отнесение"
                  value={t.allocation}
                  onChange={(v) => upd(i, { allocation: v as CustomTax["allocation"] })}
                  options={[
                    ["expense", "Вычитаемый (I21)"],
                    ["profit", "За счёт прибыли (I24)"],
                  ]}
                />
                {t.base === "formula" && (
                  <EField
                    label="Формула базы"
                    text
                    full
                    placeholder="Напр. МАКС(C13, 0) — коды строк отчётов, функции языка формул"
                    value={t.formula ?? ""}
                    onChange={(v) => upd(i, { formula: v })}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      <button type="button" className="add-row" onClick={add}>
        ＋&nbsp;&nbsp;Добавить налог
      </button>
    </div>
  );
}

/** Вкладка «Проект» (макет «Этап 5»): секции-карточки 01–05 + настраиваемые налоги. */
export function GeneralTab({ header, settings, environment, onHeader, onSettings, onEnvironment }: Props) {
  const set = (patch: Partial<ProjectSettings>) => onSettings({ ...settings, ...patch });

  const durationErr = header.duration_months < 1 ? "Минимум 1 месяц" : "";
  const liqErr = !isShare(settings.liquidation_recovery_rate) ? "Значение должно быть от 0 до 1" : "";
  const benefitErr = !isShare(settings.profit_tax_benefit_share) ? "Значение должно быть от 0 до 1" : "";
  const lossLimit = settings.loss_carryforward_limit ?? "0.5";
  const lossErr = !isShare(lossLimit) ? "Значение должно быть от 0 до 1" : "";
  const openingLoss = settings.opening_tax_loss ?? "0";
  const openingValue = parseModelNumber(openingLoss);
  const openingErr = !Number.isFinite(openingValue) || openingValue < 0
    ? "Сумма от нуля и больше" : "";
  // Вторая валюта настроена → показываем ставку дисконтирования во второй валюте (gap 1.4).
  const fxNum = (v: string | number | undefined | null) => Number(String(v ?? "").replace(",", "."));
  const hasSecondCurrency =
    (environment.fx_rate ?? []).some((v) => fxNum(v) > 0) ||
    (fxNum(environment.fx_open) > 0 && fxNum(environment.fx_open) !== 1);

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
        {hasSecondCurrency && (
          <EPercentField
            label="Ставка дисконтирования (2-я валюта)"
            suffix="% / год"
            hint="0 — выключено. При ставке > 0 показатели дублируются во второй валюте: поток пересчитывается по курсу второй валюты."
            value={settings.discount_rate_annual_foreign ?? "0"}
            onChange={(v) => set({ discount_rate_annual_foreign: v })}
          />
        )}
        <ESelect
          label="Расчёты на конец горизонта"
          hint={RELEASE_HINT}
          value={settings.release_working_capital === false ? "off" : "on"}
          onChange={(v) => set({ release_working_capital: v === "on" })}
          options={[
            ["on", "Закрывать в последнем месяце"],
            ["off", "Не учитывать"],
          ]}
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
        <EField
          label="Перенос убытков прошлых лет"
          suffix="доля"
          hint="Какую долю базы могут закрыть убытки прошлых налоговых лет: 0,5 — норма п. 2.1 ст. 283 НК РФ (по 2030 г.), 1 — без ограничения. Убыток своего года гасит прибыль этого года целиком"
          error={lossErr}
          value={lossLimit}
          onChange={(v) => set({ loss_carryforward_limit: v })}
        />
        <EField
          label="Налоговый убыток на старте"
          suffix="₽"
          hint="Неиспользованный налоговый убыток прошлых лет на дату старта — у действующего бизнеса он почти всегда есть. Гасит базу под той же долей, что и убытки горизонта. 0 — нет"
          error={openingErr}
          value={openingLoss}
          onChange={(v) => set({ opening_tax_loss: v })}
        />
        <EPercentField
          label="Ставка рефинансирования ЦБ"
          suffix="% / год"
          hint="0 — нормирование процентов выключено. Проценты вычитаемы в пределах ставки ЦБ × коэффициент, сверх — из прибыли"
          value={settings.cb_refinancing_rate ?? "0"}
          onChange={(v) => set({ cb_refinancing_rate: v })}
        />
        <EField
          label="Коэффициент норматива процентов"
          suffix="×"
          hint="Множитель к ставке ЦБ (напр. 1,25 или 1,5) для предела вычитаемых процентов"
          value={settings.interest_norm_multiple ?? "1"}
          onChange={(v) => set({ interest_norm_multiple: v })}
        />
        <EPercentField
          label="Страховые взносы с ФОТ"
          suffix="%"
          hint={CONTRIBUTION_DUE_HINT}
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
        <ESelect
          label="Уплата налога на прибыль"
          hint={PROFIT_DUE_HINT}
          value={settings.profit_tax_periodicity ?? "month"}
          onChange={(v) => set({ profit_tax_periodicity: v as ProjectSettings["profit_tax_periodicity"] })}
          options={PERIODICITY_OPTIONS}
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
          label="Уплата НДС"
          hint={VAT_DUE_HINT}
          value={settings.vat_periodicity ?? "month"}
          onChange={(v) => set({ vat_periodicity: v as ProjectSettings["vat_periodicity"] })}
          options={PERIODICITY_OPTIONS}
        />
        <ESelect
          label="Излишек входного НДС"
          hint={VAT_REFUND_HINT}
          value={settings.vat_refund === false ? "carry" : "refund"}
          onChange={(v) => set({ vat_refund: v === "refund" })}
          options={[
            ["refund", "Возмещать"],
            ["carry", "Переносить в зачёт"],
          ]}
        />
        {settings.vat_refund !== false && (
          <EField
            label="Срок возмещения"
            suffix="мес."
            hint={VAT_REFUND_LAG_HINT}
            value={settings.vat_refund_lag_months ?? 4}
            onChange={(v) => set({ vat_refund_lag_months: parseInt(v || "4", 10) || 4 })}
          />
        )}
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

      <div className="esec">
        <InflationByYear header={header} settings={settings} set={set} />
      </div>

      <CustomTaxes environment={environment} onChange={onEnvironment} />
    </div>
  );
}
