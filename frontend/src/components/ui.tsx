import { useEffect, useRef } from "react";
import type { ButtonHTMLAttributes, CSSProperties, InputHTMLAttributes, ReactNode } from "react";
import { createPortal } from "react-dom";

/* ─── Кнопка ─────────────────────────────────────────────────────────────── */

export function Button({
  variant = "primary",
  block,
  loading,
  className = "",
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger" | "link";
  block?: boolean;
  /** Показать спиннер и заблокировать кнопку. */
  loading?: boolean;
}) {
  const cls = [
    "btn",
    variant !== "primary" ? `btn--${variant}` : "",
    block ? "btn--block" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button className={cls} disabled={disabled || loading} {...props}>
      {loading && <span className="btn__spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

/* ─── Поля форм ──────────────────────────────────────────────────────────── */

/** Обёртка инпута с префиксом/суффиксом (₽, %, мес., ×…). */
function InputWrap({
  prefix,
  suffix,
  children,
}: {
  prefix?: ReactNode;
  suffix?: ReactNode;
  children: ReactNode;
}) {
  if (!prefix && !suffix) return <>{children}</>;
  const cls = [
    "input-wrap",
    prefix ? "input-wrap--prefix" : "",
    suffix ? "input-wrap--suffix" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls}>
      {prefix && <span className="input-affix input-affix--prefix">{prefix}</span>}
      {children}
      {suffix && <span className="input-affix input-affix--suffix">{suffix}</span>}
    </div>
  );
}

export function Field({
  label,
  hint,
  error,
  note,
  prefix,
  suffix,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  /** Текст ошибки: подсвечивает поле и показывает подпись. */
  error?: string;
  /** Нейтральное примечание под полем. */
  note?: string;
  prefix?: ReactNode;
  suffix?: ReactNode;
}) {
  const inputCls = ["input", error ? "input--error" : "", className ?? ""].filter(Boolean).join(" ");
  return (
    <div className="field">
      <label htmlFor={props.id}>
        {label}
        {hint && <Hint text={hint} />}
      </label>
      <InputWrap prefix={prefix} suffix={suffix}>
        <input className={inputCls} {...props} />
      </InputWrap>
      {error ? (
        <span className="field-error">{error}</span>
      ) : (
        note && <span className="field-note">{note}</span>
      )}
    </div>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  step,
  hint,
  error,
  note,
  prefix,
  suffix,
  disabled,
}: {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  step?: string;
  hint?: string;
  error?: string;
  note?: string;
  prefix?: ReactNode;
  suffix?: ReactNode;
  disabled?: boolean;
}) {
  const inputCls = ["input", error ? "input--error" : ""].filter(Boolean).join(" ");
  return (
    <div className="field">
      <label>
        {label}
        {hint && <Hint text={hint} />}
      </label>
      <InputWrap prefix={prefix} suffix={suffix}>
        <input
          className={inputCls}
          type="number"
          step={step}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      </InputWrap>
      {error ? (
        <span className="field-error">{error}</span>
      ) : (
        note && <span className="field-note">{note}</span>
      )}
    </div>
  );
}

export function SelectField({
  label,
  value,
  onChange,
  options,
  hint,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <div className="field">
      <label>
        {label}
        {hint && <Hint text={hint} />}
      </label>
      <select
        className="select"
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
    </div>
  );
}

export function CheckField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="checkbox" style={{ marginBottom: 14 }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

/** Тумблер (Этапы 7/9/11). */
export function Switch({
  label,
  checked,
  onChange,
  disabled,
}: {
  label?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className={"switch" + (disabled ? " switch--disabled" : "")}>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="switch__track" aria-hidden="true" />
      {label && <span className="switch__label">{label}</span>}
    </label>
  );
}

/** Сегмент-контрол (переключатель видов). */
export function SegmentControl<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: Array<{ value: T; label: ReactNode }>;
}) {
  return (
    <div className="seg" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={o.value === value}
          className={"seg__btn" + (o.value === value ? " seg__btn--active" : "")}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ─── Статусы и подсказки ────────────────────────────────────────────────── */

export type ChipKind = "active" | "warn" | "problem" | "info" | "neutral";

/** Чип-статус (pill с точкой): Активно / Черновик / Кассовый разрыв… */
export function Chip({ kind = "neutral", dot = true, children }: { kind?: ChipKind; dot?: boolean; children: ReactNode }) {
  return (
    <span className={"chip" + (kind !== "neutral" ? ` chip--${kind}` : "")}>
      {dot && <span className="chip__dot" aria-hidden="true" />}
      {children}
    </span>
  );
}

/** Счётчик в заголовках секций («12 показателей»). */
export function CountChip({ children }: { children: ReactNode }) {
  return <span className="count-chip">{children}</span>;
}

/** Маленькая подсказка «?» с нативным тултипом (title). */
export function Hint({ text }: { text: string }) {
  return (
    <span className="hint" title={text} aria-label={text} role="img">
      ?
    </span>
  );
}

/* ─── Карточки ───────────────────────────────────────────────────────────── */

export function Card({
  children,
  className = "",
  style,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div className={`card ${className}`} style={style}>
      {children}
    </div>
  );
}

/** Секция-карточка с номером (вкладка «Проект», Этап 5). */
export function SectionCard({
  num,
  title,
  sub,
  children,
}: {
  num?: string;
  title: string;
  sub?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="section-card">
      <div className="section-card__head">
        {num && <span className="section-card__num">{num}</span>}
        <h3 className="section-card__title" style={{ margin: 0 }}>
          {title}
        </h3>
        {sub && <span className="section-card__sub">{sub}</span>}
      </div>
      {children}
    </section>
  );
}

/** Карточка-метрика (NPV, IRR…). */
export function MetricCard({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "good" | "bad" | "neutral";
}) {
  const color = tone === "good" ? "var(--good)" : tone === "bad" ? "var(--danger)" : undefined;
  return (
    <div className="metric">
      <div className="m-label">{label}</div>
      <div className="m-value" style={color ? { color } : undefined}>
        {value}
      </div>
      {sub && <div className="field-note" style={{ marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

/* ─── Состояния данных (Р9) ──────────────────────────────────────────────── */

/** Единообразное состояние загрузки страницы. */
export function Loading({ text = "Загрузка…" }: { text?: string }) {
  return <p className="muted">{text}</p>;
}

/** Скелетон-строка/блок (пульс). */
export function Skeleton({
  width,
  height = 13,
  style,
}: {
  width?: number | string;
  height?: number | string;
  style?: CSSProperties;
}) {
  return <div className="skeleton" style={{ width, height, ...style }} aria-hidden="true" />;
}

/** Пустое состояние: dashed-карточка с заголовком и CTA. */
export function EmptyState({
  title,
  sub,
  action,
}: {
  title: string;
  sub?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__title">{title}</div>
      {sub && <div className="empty-state__sub">{sub}</div>}
      {action && <div style={{ marginTop: 6 }}>{action}</div>}
    </div>
  );
}

/** Единообразное состояние ошибки загрузки (иконка «!», текст, retry). */
export function ErrorState({
  text = "Не удалось загрузить данные.",
  onRetry,
}: {
  text?: string;
  onRetry?: () => void;
}) {
  if (!onRetry) return <p className="error">{text}</p>;
  return (
    <div className="error-state">
      <div className="error-state__ico">!</div>
      <div className="error-state__title">{text}</div>
      <Button variant="ghost" onClick={onRetry}>
        Повторить
      </Button>
    </div>
  );
}

/* ─── Модальное окно (Р8) ────────────────────────────────────────────────── */

export function Modal({
  open,
  onClose,
  title,
  sub,
  actions,
  children,
  maxWidth,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  sub?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  maxWidth?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    // Фокус внутрь модалки, чтобы Esc и таб-навигация работали сразу
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return createPortal(
    <>
      <div className="modal-overlay" onClick={onClose} />
      <div className="modal-wrap" onClick={onClose}>
        <div
          ref={ref}
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-label={title}
          tabIndex={-1}
          style={maxWidth ? { maxWidth } : undefined}
          onClick={(e) => e.stopPropagation()}
        >
          {title && <h3 className="modal__title">{title}</h3>}
          {sub && <div className="modal__sub">{sub}</div>}
          {children}
          {actions && <div className="modal__actions">{actions}</div>}
        </div>
      </div>
    </>,
    document.body,
  );
}
