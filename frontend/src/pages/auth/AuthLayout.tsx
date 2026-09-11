import { useEffect, useState } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { CubeHero } from "../../components/CubeHero";
import { IconEye, IconEyeOff } from "../../components/icons";
import { applyProduct, currentProduct, PRODUCTS, type Product } from "../../components/product";
import { getTheme, toggleTheme } from "../../components/theme";

/**
 * Общий каркас экранов входа/регистрации (макеты «Этап 2» и «Финанс Аудит — Экран 3»):
 * карточка по центру; на desktop ≥1024px — сплит с бренд-панелью 44%
 * (марка + hero-куб + фичи + чипы); тумблер темы на карточке;
 * success-оверлей с галкой и прогрессом 1.6 с до редиректа.
 *
 * Каркас один на оба продукта, содержимое панели — своё: у входа собственного продукта
 * нет, поэтому берётся последний выбранный (`currentProduct`). Иначе пользователь
 * «Аудита» после выхода видел бы зелёный экран с чужим словом в марке и обещаниями
 * бизнес-плана — то есть вход в другой продукт.
 */

interface BrandCopy {
  headline: string;
  lead: string;
  features: Array<[string, string]>;
  /** Чипы под панелью: у бизнес-плана — пример результата, у аудита — названия методик. */
  chips: string[];
}

const BRAND: Record<Product, BrandCopy> = {
  business: {
    headline: "Финансовая модель бизнеса — за вечер, а не за месяц.",
    lead: "Помесячный расчёт отчётов, показателей эффективности и оценки стоимости. "
      + "Данные — герой, интерфейс не мешает.",
    features: [
      ["4 отчёта + NPV, IRR, PI, окупаемость",
       "Прибыли и убытки · Кэш-фло · Баланс · Использование прибыли"],
      ["Оценка бизнеса 5 методами", "DCF, мультипликаторы, ликвидационная и др."],
      ["Анализ рисков и план-факт", "Чувствительность, Монте-Карло, What-If"],
    ],
    chips: ["NPV 12,48 млн ₽", "IRR 34,2%", "PI 1,82"],
  },
  // Обещания макета — «24 процедуры за шесть минут» и «средний дисконт к цене 18%» —
  // сюда не перенесены: фонового скана в продукте нет (анализ считается сразу и на
  // месте), а статистики по чужим сделкам платформа не собирает. Панель называет то,
  // что действительно посчитается по введённой отчётности.
  audit: {
    headline: "Что говорит отчётность фирмы-цели — до того, как вы её купите.",
    lead: "Аналитическая форма, коэффициенты, диагностика банкротства, реестр флагов и "
      + "оценка — из введённой отчётности. Чего в ней не видно, платформа называет прямо, "
      + "а не заполняет догадкой.",
    features: [
      ["Аналитическая форма, коэффициенты, тренды",
       "Баланс и отчёт о финрезультатах по периодам — год, квартал, месяц"],
      ["Реестр флагов, качество прибыли, обязательства",
       "Находки с денежной мерой; у кого меры нет — сказано отдельно"],
      ["Оценка DCF, торнадо и Монте-Карло, заключение",
       "По вашим допущениям: отраслевой статистики у платформы нет"],
    ],
    chips: ["Z′ Альтмана", "EBITDA норм.", "DCF"],
  },
};

function Wordmark({ product, small }: { product: Product; small?: boolean }) {
  return (
    <span className={small ? "auth-word-sm" : "auth-brand__word"}>
      Финанс<span style={{ opacity: 0.5, fontWeight: 500 }}>{PRODUCTS[product].brand}</span>
    </span>
  );
}

function BrandPanel({ product }: { product: Product }) {
  const copy = BRAND[product];
  const accent = PRODUCTS[product].cubeAccent;
  return (
    <div className="auth-brand">
      <div className="auth-brand__inner">
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <div className="auth-brand__mark">
            <CubeHero accent={accent} backdrop="transparent" showEnvironment={false}
                      showOrbit={false} pointerTilt={false} />
          </div>
          <Wordmark product={product} />
        </div>
        <div className="auth-brand__hero">
          <CubeHero accent={accent} backdrop="transparent" />
        </div>
        <div style={{ marginTop: "auto" }}>
          <div className="auth-brand__h">{copy.headline}</div>
          <div className="auth-brand__p">{copy.lead}</div>
          <div className="auth-brand__feats">
            {copy.features.map(([title, sub]) => (
              <div key={title} className="auth-brand__feat">
                <div className="auth-brand__tick">✓</div>
                <div>
                  <div className="auth-brand__feat-t">{title}</div>
                  <div className="auth-brand__feat-s">{sub}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="auth-brand__foot">
          {copy.chips.map((c) => <span className="auth-brand__chip" key={c}>{c}</span>)}
        </div>
      </div>
    </div>
  );
}

export interface AuthSuccess {
  title: string;
  sub: string;
}

/**
 * Активный продукт для экрана входа: фиксируется на монтировании (переключателя
 * продуктов до входа нет) и сразу применяется к теме — иначе токены остались бы от
 * бизнес-плана, а карточка стала бы зелёной посреди фиолетовой панели.
 */
export function useAuthProduct(): Product {
  const [product] = useState(currentProduct);
  useEffect(() => applyProduct(product), [product]);
  return product;
}

export function AuthLayout({
  product,
  title,
  subtitle,
  serverError,
  onDismissError,
  success,
  switchPrompt,
  switchAction,
  switchTo,
  children,
}: {
  product: Product;
  title: string;
  subtitle: string;
  serverError: string;
  onDismissError: () => void;
  success: AuthSuccess | null;
  switchPrompt: string;
  switchAction: string;
  switchTo: string;
  children: ReactNode;
}) {
  const [theme, setTheme] = useState(getTheme());

  return (
    <div className="auth-page">
      <div className="auth-card auth-card--split">
        <BrandPanel product={product} />
        <div className="auth-form">
          <button
            type="button"
            className="auth-theme-toggle"
            title="Переключить тему"
            onClick={() => setTheme(toggleTheme())}
          >
            <span style={{ fontSize: theme === "dark" ? 14 : 13, lineHeight: 1 }}>
              {theme === "dark" ? "☀" : "☾"}
            </span>
          </button>

          {success ? (
            <div className="auth-success">
              <div className="auth-success__cube">
                <CubeHero accent={PRODUCTS[product].cubeAccent} backdrop="transparent"
                          showEnvironment={false} />
              </div>
              <div className="auth-success__circle">
                <svg width="34" height="34" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M5 12.5l4.2 4.3L19 7.2"
                    stroke="var(--primary-text)"
                    strokeWidth="2.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              <div className="auth-success__title">{success.title}</div>
              <div className="auth-success__sub">{success.sub}</div>
              <div className="auth-success__track">
                <div className="auth-success__bar" />
              </div>
            </div>
          ) : (
            <>
              <div className="auth-form__brandrow">
                <div className="auth-mark-sm">
                  <CubeHero accent={PRODUCTS[product].cubeAccent} backdrop="transparent"
                            showEnvironment={false} showOrbit={false} pointerTilt={false} />
                </div>
                <Wordmark product={product} small />
              </div>
              <div className="auth-title">{title}</div>
              <div className="auth-subtitle">{subtitle}</div>

              {serverError && (
                <div className="auth-banner" role="alert">
                  <span className="auth-banner__ico">!</span>
                  <span style={{ flex: 1 }}>{serverError}</span>
                  <button type="button" className="auth-banner__x" onClick={onDismissError} aria-label="Скрыть">
                    ✕
                  </button>
                </div>
              )}

              {children}

              <div className="auth-divider" />
              <div className="auth-switch">
                <span>{switchPrompt}</span>
                <Link to={switchTo} className="link-btn" style={{ fontSize: 13.5 }}>
                  {switchAction}
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** Поле с иконкой-аффиксом слева (стиль «Этап 2»). */
export function AuthField({
  label,
  icon,
  error,
  hint,
  shakeKey,
  labelRight,
  trailing,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  icon: ReactNode;
  error?: string;
  hint?: string;
  /** Меняется при каждом неуспешном submit — перезапускает shake-анимацию. */
  shakeKey?: number;
  labelRight?: ReactNode;
  trailing?: ReactNode;
}) {
  const cls = ["afield", error ? "afield--error" : "", error && shakeKey ? "afield--shake" : ""]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="auth-field">
      {labelRight ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <label className="auth-label" htmlFor={input.id}>
            {label}
          </label>
          {labelRight}
        </div>
      ) : (
        <label className="auth-label" htmlFor={input.id}>
          {label}
        </label>
      )}
      <div className={cls} key={error ? shakeKey : undefined}>
        <span className="afield__affix">{icon}</span>
        <input className="afield__input" {...input} />
        {trailing}
      </div>
      {error ? <div className="auth-err">{error}</div> : hint && <div className="auth-hint">{hint}</div>}
    </div>
  );
}

/** Поле пароля с «глазом». */
export function AuthPasswordField({
  icon,
  ...props
}: Omit<Parameters<typeof AuthField>[0], "type" | "trailing"> & { icon: ReactNode }) {
  const [show, setShow] = useState(false);
  return (
    <AuthField
      {...props}
      icon={icon}
      type={show ? "text" : "password"}
      trailing={
        <button
          type="button"
          className="afield__eye"
          onClick={() => setShow((s) => !s)}
          title={show ? "Скрыть пароль" : "Показать пароль"}
          tabIndex={-1}
        >
          {show ? <IconEyeOff size={18} /> : <IconEye size={18} />}
        </button>
      }
    />
  );
}

/** Кнопка submit со спиннером и стрелкой. */
export function AuthSubmit({
  busy,
  idleText,
  busyText,
}: {
  busy: boolean;
  idleText: string;
  busyText: string;
}) {
  return (
    <button type="submit" className="auth-submit" disabled={busy}>
      {busy && <span className="btn__spinner" aria-hidden="true" />}
      <span>{busy ? busyText : idleText}</span>
      {!busy && <span style={{ fontSize: 15 }}>→</span>}
    </button>
  );
}

export function isEmailValid(v: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim());
}
