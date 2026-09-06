import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { activateInvite } from "../api/auth";
import { httpStatus, setToken } from "../api/client";
import { Button, Field } from "../components/ui";

/**
 * Активация приглашения (макет «Экран 15»).
 *
 * До этого приглашение вело в никуда: участник заводился без пароля, а способа его
 * задать не было вовсе. Сюда попадают по ссылке от пригласившего — **до** входа в
 * систему, поэтому страница живёт вне защищённых маршрутов.
 *
 * Восстановления пароля здесь нет и не будет, пока платформа не умеет отправлять
 * письма: сброс «по e-mail» без письма — это способ угнать аккаунт, зная только адрес.
 */
export function ActivatePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";

  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const mismatch = repeat.length > 0 && password !== repeat;
  const canSubmit = token && password.length >= 8 && password === repeat && !busy;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError("");
    try {
      const { access_token } = await activateInvite({
        token, password, full_name: fullName.trim(),
      });
      // Токен кладём тем же помощником, что и вход: ключ хранилища знает клиент,
      // и второе место, где он записан руками, однажды с ним разойдётся.
      setToken(access_token);
      window.location.assign("/projects");
    } catch (err) {
      const code = httpStatus(err);
      setError(
        code === 409
          ? "Приглашение уже активировано — войдите по паролю."
          : code === 400
            ? "Ссылка недействительна или устарела. Попросите пригласить вас заново."
            : "Не удалось активировать приглашение.",
      );
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div className="auth-card">
        <h1 className="auth-title">Ссылка неполная</h1>
        <p className="page-sub">
          В адресе нет кода приглашения. Откройте ссылку из письма целиком или
          попросите пригласившего прислать её заново.
        </p>
        <Button variant="ghost" onClick={() => navigate("/login")}>Ко входу</Button>
      </div>
    );
  }

  return (
    <div className="auth-card">
      <h1 className="auth-title">Задайте пароль</h1>
      <p className="page-sub" style={{ marginBottom: 18 }}>
        Вас пригласили в организацию. Придумайте пароль — после этого вы сразу
        окажетесь внутри.
      </p>

      <form onSubmit={submit}>
        <Field label="Как вас зовут" placeholder="Имя и фамилия" value={fullName}
               disabled={busy} onChange={(e) => setFullName(e.target.value)} />
        <Field label="Пароль" type="password" value={password} autoFocus disabled={busy}
               hint="Не короче 8 символов."
               onChange={(e) => setPassword(e.target.value)} />
        <Field label="Пароль ещё раз" type="password" value={repeat} disabled={busy}
               onChange={(e) => setRepeat(e.target.value)} />

        {mismatch && <div className="field-note field-note--warn">Пароли не совпадают.</div>}
        {error && <div className="error" role="alert">{error}</div>}

        <Button type="submit" disabled={!canSubmit} loading={busy}
                style={{ width: "100%", marginTop: 12 }}>
          Задать пароль и войти
        </Button>
      </form>
    </div>
  );
}
