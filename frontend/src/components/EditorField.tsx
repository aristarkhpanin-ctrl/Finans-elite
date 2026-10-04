import { useEffect, useId, useState } from "react";
import type { ReactNode } from "react";
import { fracToPct, pctToFrac } from "../format";

/**
 * Поля редактора модели (макет «Этап 5»): бокс 42px с суффиксом-юнитом
 * (%, мес., ×, доля…) за внутренней границей, моно-шрифт для чисел,
 * подсказка «?» с CSS-тултипом, ошибка под полем.
 */

/**
 * Подсказка «?» (пакет K, K5): кнопка «Подсказка» с описанием — текстом подсказки. Прежде
 * это был `span` с `tabIndex` и `aria-label`, а у безролевого элемента имя не
 * поддерживается: диктор читал «?», и сама подсказка ему не доставалась. Подсказка видна
 * в фокусе и при наведении; полю она же — описание (`aria-describedby`).
 */
export function HintBadge({ text, id }: { text: string; id?: string }) {
  const own = useId();
  const tipId = id ?? own;
  return (
    <span className="hint-wrap">
      <button type="button" className="hint-badge" aria-label="Подсказка" aria-describedby={tipId}>
        ?
      </button>
      <span className="hint-tip" role="tooltip" id={tipId}>
        {text}
      </span>
    </span>
  );
}

/**
 * Подпись, подсказка и ошибка поля связаны с самим полем (H6): `<label htmlFor>` даёт ему
 * имя, подсказка и ошибка — описание (`aria-describedby`), а не часть имени. Без связи
 * поле звалось по заполнителю («0»), а селект был безымянным — `axe-core` в матрице P13
 * нашёл 21 такой селект. Подпись **не бывает пустой**: где её не видно (строка таблицы, где
 * смысл задаёт колонка), она скрыта (`hideLabel`), но есть.
 */
function FieldShell({
  id,
  label,
  hideLabel,
  hint,
  error,
  note,
  full,
  labelRight,
  children,
}: {
  id: string;
  label: string;
  hideLabel?: boolean;
  hint?: string;
  error?: string;
  note?: string;
  full?: boolean;
  labelRight?: ReactNode;
  children: ReactNode;
}) {
  const visible = !hideLabel;
  return (
    <div className={"efield" + (full ? " efield--full" : "")}>
      {!visible && <label className="sr-only" htmlFor={id}>{label}</label>}
      {(visible || hint || labelRight) && (
        <div className="efield__labelrow">
          {visible && <label className="efield__label" htmlFor={id}>{label}</label>}
          {hint && <HintBadge text={hint} id={`${id}-hint`} />}
          {labelRight}
        </div>
      )}
      {children}
      {error ? <div className="efield__err" id={`${id}-err`}>{error}</div> : note && <div className="field-note">{note}</div>}
    </div>
  );
}

/**
 * Связи поля с подписью, подсказкой, ошибкой и единицами — одни на ввод и выбор. Единица
 * («% / год», «₽») — часть описания: без неё диктор слышал «15» и только потом, отдельным
 * текстом, «% / год» (пакет K, K5).
 */
function controlProps(id: string, hint?: string, error?: string, unit?: boolean) {
  const describedBy = [unit ? `${id}-unit` : "", hint ? `${id}-hint` : "", error ? `${id}-err` : ""]
    .filter(Boolean).join(" ");
  return { id, "aria-describedby": describedBy || undefined, "aria-invalid": error ? true : undefined };
}

export interface EFieldProps {
  /** Подпись поля — всегда; скрыть её можно (`hideLabel`), опустить нельзя. */
  label: string;
  /** Подпись только для экранного диктора: смысл поля на экране задаёт колонка/строка. */
  hideLabel?: boolean;
  value: string | number;
  onChange: (v: string) => void;
  suffix?: string;
  /** Префикс-юнит перед вводом (₽, М…). */
  prefix?: string;
  /** Элемент справа от подписи (напр. бейдж «без аморт.»). */
  labelRight?: ReactNode;
  hint?: string;
  error?: string;
  /** Нейтральное примечание под полем (напр. «→ Дебиторская задолженность»). */
  note?: string;
  full?: boolean;
  /** Текстовое поле (Inter вместо моно, inputmode text). */
  text?: boolean;
  /** Поле даты. */
  date?: boolean;
  placeholder?: string;
  disabled?: boolean;
}

export function EField({
  label,
  hideLabel,
  value,
  onChange,
  suffix,
  prefix,
  labelRight,
  hint,
  error,
  note,
  full,
  text,
  date,
  placeholder,
  disabled,
}: EFieldProps) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} hideLabel={hideLabel} hint={hint} error={error} note={note}
                full={full} labelRight={labelRight}>
      <div className={"efield__box" + (error ? " efield__box--error" : "")}>
        {prefix && <span className="efield__prefix" id={suffix ? undefined : `${id}-unit`}>{prefix}</span>}
        <input
          {...controlProps(id, hint, error, !!(prefix || suffix))}
          className={"efield__input" + (text || date ? " efield__input--text" : "")}
          type={date ? "date" : "text"}
          inputMode={text || date ? undefined : "decimal"}
          placeholder={placeholder ?? (text ? "" : "0")}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
        {suffix && <span className="efield__suffix" id={`${id}-unit`}>{suffix}</span>}
      </div>
    </FieldShell>
  );
}

export function ESelect({
  label,
  hideLabel,
  value,
  onChange,
  options,
  hint,
  error,
  full,
  disabled,
}: {
  label: string;
  hideLabel?: boolean;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
  hint?: string;
  error?: string;
  full?: boolean;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} hideLabel={hideLabel} hint={hint} error={error} full={full}>
      <div className={"efield__box" + (error ? " efield__box--error" : "")}>
        <select
          {...controlProps(id, hint, error)}
          className="efield__select"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        >
          {options.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <span className="efield__chev" aria-hidden="true">▾</span>
      </div>
    </FieldShell>
  );
}

/**
 * Процентное поле (Р10): модель хранит долю («0.18»), UI показывает «18».
 * Черновик набирается локально; в модель уходит только валидная доля,
 * поэтому промежуточные состояния («18,» и т.п.) не сбрасывают ввод.
 */
export function EPercentField({
  value,
  onChange,
  ...rest
}: Omit<EFieldProps, "value" | "onChange" | "text" | "date"> & {
  value: string | null | undefined;
  onChange: (frac: string) => void;
}) {
  const [draft, setDraft] = useState(() => fracToPct(value));

  useEffect(() => {
    // Внешнее изменение модели (discard/загрузка) — пересинхронизировать черновик
    const canonical = value ?? "";
    if (pctToFrac(draft) !== canonical && !(draft === "" && canonical === "")) {
      setDraft(fracToPct(value));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <EField
      {...rest}
      value={draft}
      onChange={(v) => {
        setDraft(v);
        const frac = pctToFrac(v);
        if (frac !== "" || v.trim() === "") onChange(frac === "" ? "0" : frac);
      }}
    />
  );
}
