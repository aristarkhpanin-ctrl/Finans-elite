import { useEffect, useRef, useState, type FormEvent } from "react";
import { httpDetail, httpStatus } from "../api/client";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { IconBuilding, IconLock, IconMail, IconUser } from "../components/icons";
import { PRODUCTS } from "../components/product";
import {
  AuthLayout, AuthPasswordField, AuthField, AuthSubmit, isEmailValid, useAuthProduct,
} from "./auth/AuthLayout";
import { usePageTitle } from "../pageTitle";

const REDIRECT_DELAY_MS = 1600;
const MIN_PASSWORD = 8;

/** Регистрация одна на платформу; называется только то, ради чего пришли. */
const LEAD: Record<string, string> = {
  business: "Зарегистрируйтесь — и создайте организацию для своих финансовых моделей.",
  audit: "Зарегистрируйтесь — и создайте организацию для дел о фирмах-целях.",
};

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const product = useAuthProduct();
  usePageTitle("Регистрация");
  const [form, setForm] = useState({ full_name: "", email: "", password: "", organization_name: "" });
  // Согласие на обработку ПД — **отдельная отметка**, не входящая в принятие оферты
  // (ч. 1 ст. 9 152-ФЗ в ред. с 1.09.2025). По умолчанию снята: поставленная заранее
  // галочка — не согласие, а его имитация.
  const [consent, setConsent] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const [shakeKey, setShakeKey] = useState(0);
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const timer = useRef<number>();

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));
  const blur = (k: string) => () => setTouched((t) => ({ ...t, [k]: true }));
  const show = (f: string) => submitted || touched[f];

  const errors = {
    full_name: show("full_name") && !form.full_name.trim() ? "Укажите ФИО" : "",
    email: show("email")
      ? !form.email.trim()
        ? "Введите email"
        : !isEmailValid(form.email)
          ? "Неверный формат email"
          : ""
      : "",
    password: show("password")
      ? !form.password
        ? "Введите пароль"
        : form.password.length < MIN_PASSWORD
          ? "Минимум 8 символов"
          : ""
      : "",
    organization_name:
      show("organization_name") && !form.organization_name.trim() ? "Укажите название организации" : "",
    consent: submitted && !consent
      ? "Без согласия на обработку персональных данных зарегистрироваться нельзя"
      : "",
  };

  function hasBlockingErrors(): boolean {
    return (
      !form.full_name.trim() ||
      !form.email.trim() ||
      !isEmailValid(form.email) ||
      !form.password ||
      form.password.length < MIN_PASSWORD ||
      !form.organization_name.trim() ||
      !consent
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    setServerError("");
    if (hasBlockingErrors()) {
      setShakeKey((k) => k + 1);
      return;
    }
    setBusy(true);
    try {
      await register({ ...form, pd_consent: consent });
      setSuccess(true);
      // Новая организация ведёт в тот продукт, из которого пришли на регистрацию:
      // «Аудит» с зелёного списка проектов начинался бы не с того экрана.
      timer.current = window.setTimeout(
        () => navigate(PRODUCTS[product].home), REDIRECT_DELAY_MS);
    } catch (err: unknown) {
      setServerError(
        httpStatus(err) === 409
          ? "Этот email уже зарегистрирован"
          // Отказ по паролю сервер называет словами («слишком известен», «подряд идущие
          // клавиши», «повторяет ваш адрес»). Заменять их общим «не удалось» значило бы
          // отправить человека перебирать варианты вслепую — и он придёт к «Parol1234!».
          : httpStatus(err) === 422 && httpDetail(err)
            ? httpDetail(err)!
            : "Не удалось создать аккаунт. Попробуйте ещё раз.",
      );
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      product={product}
      title="Создать аккаунт"
      subtitle={LEAD[product]}
      serverError={serverError}
      onDismissError={() => setServerError("")}
      success={
        success
          ? { title: "Аккаунт создан", sub: "Организация готова. Перенаправляем в рабочую область…" }
          : null
      }
      switchPrompt="Уже есть аккаунт?"
      switchAction="Войти"
      switchTo="/login"
    >
      <form className="auth-fields" onSubmit={onSubmit} noValidate>
        <AuthField
          id="full_name"
          label="ФИО"
          icon={<IconUser size={17} />}
          type="text"
          placeholder="Иван Петров"
          autoComplete="name"
          value={form.full_name}
          disabled={busy}
          error={errors.full_name}
          shakeKey={shakeKey}
          onChange={set("full_name")}
          onBlur={blur("full_name")}
        />
        <AuthField
          id="email"
          label="Email"
          icon={<IconMail size={17} />}
          type="text"
          inputMode="email"
          placeholder="name@company.ru"
          autoComplete="email"
          value={form.email}
          disabled={busy}
          error={errors.email}
          shakeKey={shakeKey}
          onChange={set("email")}
          onBlur={blur("email")}
        />
        <AuthPasswordField
          id="password"
          label="Пароль"
          icon={<IconLock size={17} />}
          placeholder="Не менее 8 символов"
          autoComplete="new-password"
          value={form.password}
          disabled={busy}
          error={errors.password}
          hint="Минимум 8 символов"
          shakeKey={shakeKey}
          onChange={set("password")}
          onBlur={blur("password")}
        />
        <AuthField
          id="organization_name"
          label="Название организации"
          icon={<IconBuilding size={17} />}
          type="text"
          placeholder="ООО «Ваша компания»"
          autoComplete="organization"
          value={form.organization_name}
          disabled={busy}
          error={errors.organization_name}
          shakeKey={shakeKey}
          onChange={set("organization_name")}
          onBlur={blur("organization_name")}
        />
        <label className="auth-remember auth-consent">
          <input type="checkbox" checked={consent} disabled={busy}
                 aria-invalid={errors.consent ? true : undefined}
                 aria-describedby={errors.consent ? "consent-error" : undefined}
                 onChange={(e) => setConsent(e.target.checked)} />
          <span>
            Даю{" "}
            <Link to="/legal/consent" target="_blank" rel="noopener">
              согласие на обработку персональных данных
            </Link>
          </span>
        </label>
        {errors.consent && (
          <span className="field-error" id="consent-error">{errors.consent}</span>
        )}
        <AuthSubmit busy={busy} idleText="Создать аккаунт" busyText="Создаём…" />
        {/* Оферта принимается регистрацией (для оплаты — оплатой), и об этом сказано
            здесь, рядом с кнопкой; согласие на обработку ПД — отдельной отметкой выше. */}
        <div className="auth-legal">
          Создавая аккаунт, вы принимаете условия{" "}
          <Link to="/legal/offer" target="_blank" rel="noopener">оферты</Link>. Как
          обрабатываются данные — в{" "}
          <Link to="/legal/privacy" target="_blank" rel="noopener">
            политике обработки персональных данных
          </Link>.
        </div>
      </form>
    </AuthLayout>
  );
}
