import { useEffect, useRef, useState, type FormEvent } from "react";
import { httpStatus } from "../api/client";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { IconLock, IconMail } from "../components/icons";
import { PRODUCTS } from "../components/product";
import {
  AuthLayout, AuthPasswordField, AuthField, AuthSubmit, isEmailValid, useAuthProduct,
} from "./auth/AuthLayout";

const REDIRECT_DELAY_MS = 1600; // длительность прогресса success-оверлея

/**
 * Подзаголовок называет продукт, в который ведёт вход: с зелёного «Элита» и с
 * фиолетового «Аудита» открываются разные рабочие области, и после входа
 * пользователь попадает именно туда, откуда пришёл.
 */
const LEAD: Record<string, string> = {
  business: "Войдите, чтобы продолжить работу с моделями и отчётами.",
  audit: "Войдите, чтобы продолжить работу с делами и заключениями.",
};

/**
 * Восстановления пароля в продукте нет: сбросить его не может ни пользователь, ни
 * администратор организации (приглашение задаёт пароль лишь однажды). Ссылка «Забыли
 * пароль?» из макета вела бы в никуда, а молчание — к поиску того, чего нет; поэтому
 * отсутствие названо прямо.
 */
const NO_RESET = "Самостоятельного восстановления пароля пока нет.";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const product = useAuthProduct();
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
      timer.current = window.setTimeout(
        () => navigate(PRODUCTS[product].home), REDIRECT_DELAY_MS);
    } catch (err: unknown) {
      const status = httpStatus(err);
      setServerError(
        status === 401
          ? "Неверный email или пароль"
          // Ограничение — по числу попыток с адреса за минуту, и оно не именное:
          // «осталось 3 попытки до блокировки» из макета обещало бы счётчик на
          // учётную запись, которого сервер не ведёт.
          : status === 429
            ? "Слишком много попыток входа. Подождите минуту и попробуйте снова."
            : "Не удалось выполнить вход. Попробуйте ещё раз.",
      );
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      product={product}
      title="С возвращением"
      subtitle={LEAD[product]}
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
          hint={NO_RESET}
          shakeKey={shakeKey}
          onChange={(e) => setPassword(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, password: true }))}
        />
        <AuthSubmit busy={busy} idleText="Войти" busyText="Входим…" />
      </form>
    </AuthLayout>
  );
}
