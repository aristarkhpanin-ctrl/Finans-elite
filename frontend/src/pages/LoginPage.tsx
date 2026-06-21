import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Button, Card, Field } from "../components/ui";

export function LoginPage() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login({ email, password });
      navigate("/projects");
    } catch (err: any) {
      setError(err?.response?.status === 401 ? t("auth.invalid") : t("auth.genericError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <Card className="auth-card">
        <h1>{t("auth.login")}</h1>
        <p className="muted" style={{ marginTop: 0 }}>{t("app.title")}</p>
        <form onSubmit={onSubmit}>
          <Field id="email" label={t("auth.email")} type="email" value={email}
                 autoComplete="email" required onChange={(e) => setEmail(e.target.value)} />
          <Field id="password" label={t("auth.password")} type="password" value={password}
                 autoComplete="current-password" required onChange={(e) => setPassword(e.target.value)} />
          {error && <p className="error">{error}</p>}
          <Button type="submit" block disabled={busy}>{t("auth.signIn")}</Button>
        </form>
        <p className="muted" style={{ marginTop: 14, textAlign: "center" }}>
          <Link to="/register">{t("auth.noAccount")}</Link>
        </p>
      </Card>
    </div>
  );
}
