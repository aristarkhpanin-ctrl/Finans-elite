import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fracToPct, pctToFrac } from "../format";

/**
 * Поля редактора модели (макет «Этап 5»): бокс 42px с суффиксом-юнитом
 * (%, мес., ×, доля…) за внутренней границей, моно-шрифт для чисел,
 * подсказка «?» с CSS-тултипом, ошибка под полем.
 */

export function HintBadge({ text }: { text: string }) {
  return (
    <span className="hint-wrap">
      <span className="hint-badge" tabIndex={0} aria-label={text}>
        ?
      </span>
      <span className="hint-tip" role="tooltip">
        {text}
      </span>
    </span>
  );
}

function FieldShell({
  label,
  hint,
  error,
  note,
  full,
  labelRight,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  note?: string;
  full?: boolean;
  labelRight?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={"efield" + (full ? " efield--full" : "")}>
      <div className="efield__labelrow">
        <label className="efield__label">{label}</label>
        {hint && <HintBadge text={hint} />}
        {labelRight}
      </div>
      {children}
      {error ? <div className="efield__err">{error}</div> : note && <div className="field-note">{note}</div>}
    </div>
  );
}

export interface EFieldProps {
  label: string;
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
  return (
    <FieldShell label={label} hint={hint} error={error} note={note} full={full} labelRight={labelRight}>
      <div className={"efield__box" + (error ? " efield__box--error" : "")}>
        {prefix && <span className="efield__prefix">{prefix}</span>}
        <input
          className={"efield__input" + (text || date ? " efield__input--text" : "")}
          type={date ? "date" : "text"}
          inputMode={text || date ? undefined : "decimal"}
          placeholder={placeholder ?? (text ? "" : "0")}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
        {suffix && <span className="efield__suffix">{suffix}</span>}
      </div>
    </FieldShell>
  );
}

export function ESelect({
  label,
  value,
  onChange,
  options,
  hint,
  error,
  full,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
  hint?: string;
  error?: string;
  full?: boolean;
  disabled?: boolean;
}) {
  return (
    <FieldShell label={label} hint={hint} error={error} full={full}>
      <div className={"efield__box" + (error ? " efield__box--error" : "")}>
        <select
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
        <span className="efield__chev">▾</span>
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
