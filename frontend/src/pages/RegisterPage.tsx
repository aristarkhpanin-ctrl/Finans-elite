import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { IconBuilding, IconLock, IconMail, IconUser } from "../components/icons";
import { AuthLayout, AuthPasswordField, AuthField, AuthSubmit, isEmailValid } from "./auth/AuthLayout";

const REDIRECT_DELAY_MS = 1600;
const MIN_PASSWORD = 8;

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", organization_name: "" });
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
  };

  function hasBlockingErrors(): boolean {
    return (
      !form.full_name.trim() ||
      !form.email.trim() ||
      !isEmailValid(form.email) ||
      !form.password ||
      form.password.length < MIN_PASSWORD ||
      !form.organization_name.trim()
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
      await register(form);
      setSuccess(true);
      timer.current = window.setTimeout(() => navigate("/projects"), REDIRECT_DELAY_MS);
    } catch (err: any) {
      setServerError(
        err?.response?.status === 409
          ? "Этот email уже зарегистрирован"
          : "Не удалось создать аккаунт. Попробуйте ещё раз.",
      );
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Создать аккаунт"
      subtitle="Зарегистрируйтесь — и создайте организацию для своих финансовых моделей."
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
        <AuthSubmit busy={busy} idleText="Создать аккаунт" busyText="Создаём…" />
        <div className="auth-legal">
          Создавая аккаунт, вы принимаете <span>Условия</span> и <span>Политику конфиденциальности</span>.
        </div>
      </form>
    </AuthLayout>
  );
}
