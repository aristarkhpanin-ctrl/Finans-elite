import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { getTheme, toggleTheme, type Theme } from "./theme";
import { Button } from "./ui";

export function Layout() {
  const { t } = useTranslation();
  const { user, organizations, currentOrgId, selectOrg, logout } = useAuth();
  const navigate = useNavigate();
  const [theme, setTheme] = useState<Theme>(getTheme());

  return (
    <div className="app">
      <header className="appbar">
        <span className="brand">{t("app.title")}</span>
        <nav className="nav">
          <NavLink to="/projects" className={({ isActive }) => (isActive ? "nav-link nav-link--active" : "nav-link")}>
            {t("nav.projects")}
          </NavLink>
          <NavLink to="/organization" className={({ isActive }) => (isActive ? "nav-link nav-link--active" : "nav-link")}>
            Организация
          </NavLink>
        </nav>
        {organizations.length > 0 && (
          <select
            className="select"
            value={currentOrgId ?? ""}
            onChange={(e) => {
              selectOrg(e.target.value);
              location.reload();
            }}
          >
            {organizations.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name} · {o.role}
              </option>
            ))}
          </select>
        )}
        <span className="spacer" />
        <Button variant="ghost" onClick={() => setTheme(toggleTheme())}>
          {theme === "dark" ? "☀︎" : "☾"}
        </Button>
        {user && <span className="muted">{user.email}</span>}
        <Button
          variant="ghost"
          onClick={() => {
            logout();
            navigate("/login");
          }}
        >
          {t("nav.logout")}
        </Button>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
