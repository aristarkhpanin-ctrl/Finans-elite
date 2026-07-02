import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { IconLock, IconMail } from "../components/icons";
import { AuthLayout, AuthPasswordField, AuthField, AuthSubmit, isEmailValid } from "./auth/AuthLayout";

const REDIRECT_DELAY_MS = 1600; // длительность прогресса success-оверлея

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const [shakeKey, setShakeKey] = useState(0);
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const timer = useRef<number>();

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const show = (f: string) => submitted || touched[f];
  const errEmail = show("email")
    ? !email.trim()
      ? "Введите email"
      : !isEmailValid(email)
        ? "Неверный формат email"
        : ""
    : "";
  const errPass = show("password") && !password ? "Введите пароль" : "";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    setServerError("");
    if (!email.trim() || !isEmailValid(email) || !password) {
      setShakeKey((k) => k + 1);
      return;
    }
    setBusy(true);
    try {
      await login({ email, password });
      setSuccess(true);
      timer.current = window.setTimeout(() => navigate("/projects"), REDIRECT_DELAY_MS);
    } catch (err: any) {
      setServerError(
        err?.response?.status === 401
          ? "Неверный email или пароль"
          : "Не удалось выполнить вход. Попробуйте ещё раз.",
      );
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="С возвращением"
      subtitle="Войдите, чтобы продолжить работу с моделями и отчётами."
      serverError={serverError}
      onDismissError={() => setServerError("")}
      success={success ? { title: "Вход выполнен", sub: "Перенаправляем в рабочую область…" } : null}
      switchPrompt="Нет аккаунта?"
      switchAction="Регистрация"
      switchTo="/register"
    >
      <form className="auth-fields" onSubmit={onSubmit} noValidate>
        <AuthField
          id="email"
          label="Email"
          icon={<IconMail size={17} />}
          type="text"
          inputMode="email"
          placeholder="name@company.ru"
          autoComplete="email"
          value={email}
          disabled={busy}
          error={errEmail}
          shakeKey={shakeKey}
          onChange={(e) => setEmail(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, email: true }))}
        />
        <AuthPasswordField
          id="password"
          label="Пароль"
          icon={<IconLock size={17} />}
          placeholder="Ваш пароль"
          autoComplete="current-password"
          value={password}
          disabled={busy}
          error={errPass}
          shakeKey={shakeKey}
          onChange={(e) => setPassword(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, password: true }))}
        />
        <AuthSubmit busy={busy} idleText="Войти" busyText="Входим…" />
      </form>
    </AuthLayout>
  );
}
