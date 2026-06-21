import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

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

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}
