import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Button, Card, Field } from "../components/ui";

export function RegisterPage() {
  const { t } = useTranslation();
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", organization_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await register(form);
      navigate("/projects");
    } catch (err: any) {
      setError(err?.response?.status === 409 ? t("auth.emailTaken") : t("auth.genericError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <Card className="auth-card">
        <h1>{t("auth.register")}</h1>
        <p className="muted" style={{ marginTop: 0 }}>{t("app.title")}</p>
        <form onSubmit={onSubmit}>
          <Field id="full_name" label={t("auth.fullName")} value={form.full_name} onChange={set("full_name")} />
          <Field id="org" label={t("auth.orgName")} value={form.organization_name} required onChange={set("organization_name")} />
          <Field id="email" label={t("auth.email")} type="email" value={form.email}
                 autoComplete="email" required onChange={set("email")} />
          <Field id="password" label={t("auth.password")} type="password" value={form.password}
                 autoComplete="new-password" required minLength={6} onChange={set("password")} />
          {error && <p className="error">{error}</p>}
          <Button type="submit" block disabled={busy}>{t("auth.signUp")}</Button>
        </form>
        <p className="muted" style={{ marginTop: 14, textAlign: "center" }}>
          <Link to="/login">{t("auth.haveAccount")}</Link>
        </p>
      </Card>
    </div>
  );
}
