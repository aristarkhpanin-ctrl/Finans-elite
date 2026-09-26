import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { getCapabilities, requestPasswordReset } from "../api/auth";
import { httpDetail, httpStatus } from "../api/client";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { IconLock, IconMail } from "../components/icons";
import { PRODUCTS } from "../components/product";
import { Button, Field, Modal } from "../components/ui";
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
 * Когда почта в этой установке не настроена, самостоятельного восстановления нет:
 * сброс «по одному лишь адресу» без письма — способ угнать аккаунт. Тупика при этом
 * тоже нет — подпись называет реальный путь вместо ссылки «Забыли пароль?», которая
 * вела бы в никуда. Настроена почта — появляется и ссылка (D1).
 */
const NO_RESET = "Забыли пароль — ссылку на сброс выдаёт администратор организации.";

/** Ключ, под которым вход передаёт своё примечание рабочей области. */
export const LOGIN_NOTICE_KEY = "finans:login-notice";

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
  /**
   * «Запомнить меня»: вход живёт 30 дней вместо суток. Длинный срок перестал быть
   * опасным, когда появился реестр входов (C1) — человек видит свои сеансы в профиле и
   * закрывает лишние. По умолчанию выключено: сутки — разумная цена за чужой ноутбук.
   */
  const [remember, setRemember] = useState(false);
  /**
   * Код второго фактора (C2). Поле появляется **после** того, как сервер попросил код
   * (428): показывать его всем значило бы спрашивать код у тех, у кого второго фактора
   * нет, — и пугать их на ровном месте.
   */
  const [totpCode, setTotpCode] = useState("");
  const [needCode, setNeedCode] = useState(false);
  const [success, setSuccess] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);
  const timer = useRef<number>();

  /**
   * Умеет ли эта установка отправлять письма (D1) — спрашиваем сервер, а не решаем сами.
   * Пока ответа нет, ссылки «Забыли пароль?» не показываем: обещание, данное на догадке,
   * ничем не лучше тупика.
   */
  const { data: caps } = useQuery({ queryKey: ["capabilities"],
                                    queryFn: getCapabilities, staleTime: Infinity });
  const canMail = caps?.mail === true;

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
      const notice = await login({ email, password, remember, totp_code: totpCode });
      // Примечание входа («вошли по резервному коду, осталось N») показывается уже в
      // рабочей области: здесь страница через мгновение сменится, и прочесть его не
      // успеют. Молча съеденный резервный код кончится в самый неподходящий момент.
      if (notice) sessionStorage.setItem(LOGIN_NOTICE_KEY, notice);
      setSuccess(true);
      timer.current = window.setTimeout(
        () => navigate(PRODUCTS[product].home), REDIRECT_DELAY_MS);
    } catch (err: unknown) {
      const status = httpStatus(err);
      if (status === 428) {
        // Пароль верен — нужен второй шаг. Не 401: тот отправил бы человека проверять
        // пароль, которого он не путал.
        setNeedCode(true);
        setServerError(httpDetail(err) ?? "Введите код из приложения");
        setBusy(false);
        return;
      }
      if (needCode && (status === 401 || status === 429)) {
        // Неверный код или пауза после подбора — причину сервер называет словами.
        setServerError(httpDetail(err) ?? "Неверный код");
        setBusy(false);
        return;
      }
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
          // Ссылка появляется, только когда письма действительно уходят: нарисованная
          // там, где почты нет, она ведёт человека в тупик.
          hint={canMail ? undefined : NO_RESET}
          labelRight={canMail ? (
            <button type="button" className="auth-link-btn"
                    onClick={() => setForgotOpen(true)}>Забыли пароль?</button>
          ) : undefined}
          shakeKey={shakeKey}
          onChange={(e) => setPassword(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, password: true }))}
        />
        {needCode && (
          <AuthField
            id="totp"
            label="Код из приложения"
            icon={<IconLock size={17} />}
            type="text"
            inputMode="numeric"
            placeholder="6 цифр или резервный код"
            autoComplete="one-time-code"
            autoFocus
            value={totpCode}
            disabled={busy}
            error=""
            shakeKey={shakeKey}
            onChange={(e) => setTotpCode(e.target.value)}
          />
        )}
        <label className="auth-remember">
          <input type="checkbox" checked={remember} disabled={busy}
                 onChange={(e) => setRemember(e.target.checked)} />
          <span>Запомнить меня на 30 дней</span>
        </label>
        <AuthSubmit busy={busy} idleText="Войти" busyText="Входим…" />
      </form>
      <ForgotPassword open={forgotOpen} initialEmail={email}
                      onClose={() => setForgotOpen(false)} />
    </AuthLayout>
  );
}

/**
 * «Забыли пароль»: попросить ссылку на почту (D1).
 *
 * Ответ сервера **один и тот же** для существующего, чужого и выдуманного адреса — и
 * показывается он как есть. Своего текста здесь не сочиняем: «письмо отправлено на
 * ваш адрес» было бы утверждением, которого сервер намеренно не делает, а «такого
 * адреса нет» превратило бы форму в проверялку клиентов платформы.
 */
function ForgotPassword({ open, initialEmail, onClose }: {
  open: boolean; initialEmail: string; onClose: () => void;
}) {
  const [email, setEmail] = useState(initialEmail);
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    try {
      setAnswer(await requestPasswordReset(email.trim()));
    } catch (err: unknown) {
      // Отказ сервера содержательный (почта не настроена, слишком часто) — показываем
      // его словами: своя формулировка разошлась бы с правилом на сервере.
      setError(httpDetail(err) ?? "Не удалось отправить письмо");
    }
    setBusy(false);
  }

  return (
    <Modal open={open} onClose={onClose} title="Забыли пароль" maxWidth={440}
           actions={answer ? <Button onClick={onClose}>Закрыть</Button> : (
             <>
               <Button variant="ghost" onClick={onClose}>Отмена</Button>
               <Button onClick={submit} loading={busy}
                       disabled={!isEmailValid(email)}>Прислать ссылку</Button>
             </>
           )}>
      {answer ? (
        <p className="page-sub" style={{ marginTop: 0 }}>{answer}</p>
      ) : (
        <>
          <p className="page-sub" style={{ marginTop: 0 }}>
            Пришлём ссылку, по которой можно задать новый пароль. Ссылка уходит{" "}
            <b>на сам почтовый ящик</b> и действует неделю. Если включён второй фактор,
            код из приложения спросят и там — письмо его не заменяет.
          </p>
          <Field label="Email" value={email} autoFocus type="text" inputMode="email"
                 error={error || undefined}
                 onChange={(e) => setEmail(e.target.value)} />
        </>
      )}
    </Modal>
  );
}
