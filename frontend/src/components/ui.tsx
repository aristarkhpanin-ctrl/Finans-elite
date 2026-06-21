import type { ButtonHTMLAttributes, CSSProperties, InputHTMLAttributes, ReactNode } from "react";

export function Button({
  variant = "primary",
  block,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost"; block?: boolean }) {
  const cls = [
    "btn",
    variant === "ghost" ? "btn--ghost" : "",
    block ? "btn--block" : "",
    className,
  ].join(" ");
  return <button className={cls} {...props} />;
}

export function Field({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <div className="field">
      <label htmlFor={props.id}>{label}</label>
      <input className="input" {...props} />
    </div>
  );
}

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

export function NumberField({
  label,
  value,
  onChange,
  step,
}: {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  step?: string;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      <input className="input" type="number" step={step} value={value}
             onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
