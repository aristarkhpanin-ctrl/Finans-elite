import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, matchPath, useLocation, useNavigate } from "react-router-dom";
import { createOrganization, roleLabel } from "../api/org";
import { useAuth } from "../auth/AuthContext";
import { CubeHero } from "./CubeHero";
import { useToast } from "./Toast";
import { getTheme, toggleTheme, type Theme } from "./theme";
import { Button, Field, Modal } from "./ui";

/**
 * Каркас приложения (макет «Этап 3»): шапка с куб-маркой и навигацией,
 * орг-селектор с меню, тумблер темы, user-меню, мобильный drawer.
 */

/** Инициалы из названия/имени: «Финмодель Консалтинг» → «ФК». */
function initials(name: string | null | undefined, fallback = "•"): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return fallback;
  return words
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

/** Палитра аватаров организаций в списке (цикл из макета). */
const ORG_AVATAR_BG = ["", "#5E93FF", "#C77DFF"];

const NAV = [
  ["/projects", "Проекты"],
  ["/holdings", "Холдинги"],
  ["/organization", "Организация"],
] as const;

const PROJECT_MODES = [
  ["", "Редактор"],
  ["/results", "Результаты"],
  ["/analysis", "Анализ"],
] as const;

export function Layout() {
  const { user, organizations, currentOrgId, selectOrg, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const toast = useToast();
  const [theme, setTheme] = useState<Theme>(getTheme());
  const [open, setOpen] = useState<null | "org" | "user" | "mobile">(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [creating, setCreating] = useState(false);
  const [drawerOrgList, setDrawerOrgList] = useState(false);

  const currentOrg = organizations.find((o) => o.id === currentOrgId) ?? organizations[0];
  const multi = organizations.length > 1;

  // Внутри проекта? (для блока «Текущий проект» в drawer)
  const projectMatch = matchPath("/projects/:id/*", pathname) ?? matchPath("/projects/:id", pathname);
  const projectId = projectMatch?.params.id;

  useEffect(() => {
    setOpen(null);
    setDrawerOrgList(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const themeLabel = theme === "dark" ? "Тёмная" : "Светлая";

  function switchOrg(orgId: string) {
    if (orgId === currentOrgId) {
      setOpen(null);
      return;
    }
    selectOrg(orgId);
    // Полная перезагрузка: сбрасывает все закэшированные данные прежней организации
    window.location.reload();
  }

  async function submitCreateOrg() {
    const name = newOrgName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const org = await createOrganization(name);
      selectOrg(org.id);
      window.location.reload();
    } catch {
      setCreating(false);
      toast("Не удалось создать организацию", { kind: "error" });
    }
  }

  function doLogout() {
    logout();
    navigate("/login");
  }

  const orgMenu = useMemo(
    () =>
      organizations.map((o, i) => ({
        ...o,
        avatarBg: ORG_AVATAR_BG[i % ORG_AVATAR_BG.length],
        active: o.id === currentOrgId,
      })),
    [organizations, currentOrgId],
  );

  return (
    <div className="app">
      <header className="shell-header">
        <div className="shell-left">
          <NavLink to="/projects" className="shell-brand" style={{ textDecoration: "none" }}>
            <div className="shell-mark">
              <CubeHero backdrop="transparent" showEnvironment={false} showOrbit={false} pointerTilt={false} />
            </div>
            <span className="shell-word">
              Финанс<span>-Элит</span>
            </span>
          </NavLink>
          <nav className="shell-nav">
            {NAV.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  "shell-nav__item" + (isActive ? " shell-nav__item--active" : "")
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="shell-right">
          {currentOrg && (
            <div className="shell-orgwrap" style={{ position: "relative" }}>
              {multi ? (
                <>
                  <button
                    type="button"
                    className="shell-orgbtn"
                    onClick={() => setOpen(open === "org" ? null : "org")}
                    aria-expanded={open === "org"}
                  >
                    <div className="org-avatar">{initials(currentOrg.name)}</div>
                    <span className="shell-orgname">{currentOrg.name}</span>
                    <span className="shell-chev">▾</span>
                  </button>
                  {open === "org" && (
                    <div className="menu menu--org">
                      <div className="menu__head">Организации</div>
                      {orgMenu.map((o) => (
                        <button
                          key={o.id}
                          type="button"
                          className={"menu__item" + (o.active ? " menu__item--active" : "")}
                          onClick={() => switchOrg(o.id)}
                        >
                          <div
                            className="org-avatar org-avatar--30"
                            style={o.avatarBg ? { background: o.avatarBg, color: "#fff" } : undefined}
                          >
                            {initials(o.name)}
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div className="menu__name">{o.name}</div>
                            <div className="menu__role">{roleLabel(o.role)}</div>
                          </div>
                          {o.active && <span className="menu__check">✓</span>}
                        </button>
                      ))}
                      <div className="menu__div" />
                      <button
                        type="button"
                        className="menu__link"
                        onClick={() => {
                          setOpen(null);
                          setNewOrgName("");
                          setCreateOpen(true);
                        }}
                      >
                        <span className="menu__ico">＋</span>Создать организацию
                      </button>
                      <button
                        type="button"
                        className="menu__link"
                        onClick={() => {
                          setOpen(null);
                          navigate("/organization");
                        }}
                      >
                        <span className="menu__ico">⚙</span>Управление организацией
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <div className="shell-orgbtn shell-orgbtn--static">
                  <div className="org-avatar">{initials(currentOrg.name)}</div>
                  <span className="shell-orgname">{currentOrg.name}</span>
                </div>
              )}
            </div>
          )}

          <button
            type="button"
            className="icon-btn38"
            title="Переключить тему"
            onClick={() => setTheme(toggleTheme())}
          >
            <span style={{ fontSize: theme === "dark" ? 15 : 14 }}>{theme === "dark" ? "☀" : "☾"}</span>
          </button>

          {user && (
            <div className="shell-userwrap" style={{ position: "relative" }}>
              <button
                type="button"
                className="shell-userbtn"
                onClick={() => setOpen(open === "user" ? null : "user")}
                aria-expanded={open === "user"}
              >
                <div className="user-avatar">{initials(user.full_name || user.email)}</div>
                <span className="shell-useremail">{user.email}</span>
                <span className="shell-chev">▾</span>
              </button>
              {open === "user" && (
                <div className="menu menu--user">
                  <div style={{ display: "flex", alignItems: "center", gap: 11, padding: 9 }}>
                    <div className="user-avatar user-avatar--lg">{initials(user.full_name || user.email)}</div>
                    <div style={{ minWidth: 0 }}>
                      {user.full_name && <div className="menu__uname">{user.full_name}</div>}
                      <div className="menu__umail">{user.email}</div>
                    </div>
                  </div>
                  <div className="menu__div" />
                  <button
                    type="button"
                    className="menu__link"
                    onClick={() => setTheme(toggleTheme())}
                  >
                    <span className="menu__ico">◐</span>Сменить тему
                    <span style={{ marginLeft: "auto", font: "600 11px var(--font-ui)", color: "var(--subtle)" }}>
                      {themeLabel}
                    </span>
                  </button>
                  <div className="menu__div" />
                  <button type="button" className="menu__link menu__link--danger" onClick={doLogout}>
                    <span className="menu__ico">⇥</span>Выйти
                  </button>
                </div>
              )}
            </div>
          )}

          <button type="button" className="icon-btn38 shell-burger-btn" title="Меню" onClick={() => setOpen("mobile")}>
            <div className="shell-burger">
              <span />
              <span />
              <span />
            </div>
          </button>
        </div>
      </header>

      {(open === "org" || open === "user") && <div className="menu-overlay" onClick={() => setOpen(null)} />}

      {open === "mobile" && (
        <>
          <div className="drawer-overlay" onClick={() => setOpen(null)} />
          <div className="drawer" role="dialog" aria-label="Меню">
            <div className="drawer__head">
              <span className="shell-word">
                Финанс<span>-Элит</span>
              </span>
              <button type="button" className="icon-btn38" onClick={() => setOpen(null)} aria-label="Закрыть">
                <span style={{ fontSize: 15, color: "var(--muted)" }}>✕</span>
              </button>
            </div>

            {currentOrg && (
              <>
                <button
                  type="button"
                  className="drawer__org"
                  onClick={() => multi && setDrawerOrgList((v) => !v)}
                  style={multi ? undefined : { cursor: "default" }}
                >
                  <div className="org-avatar">{initials(currentOrg.name)}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="menu__name">{currentOrg.name}</div>
                    <div className="menu__role">
                      {roleLabel(currentOrg.role)}
                      {multi && " · сменить"}
                    </div>
                  </div>
                  {multi && <span className="shell-chev">▾</span>}
                </button>
                {drawerOrgList &&
                  orgMenu
                    .filter((o) => !o.active)
                    .map((o) => (
                      <button key={o.id} type="button" className="menu__item" onClick={() => switchOrg(o.id)}>
                        <div
                          className="org-avatar org-avatar--30"
                          style={o.avatarBg ? { background: o.avatarBg, color: "#fff" } : undefined}
                        >
                          {initials(o.name)}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className="menu__name">{o.name}</div>
                          <div className="menu__role">{roleLabel(o.role)}</div>
                        </div>
                      </button>
                    ))}
              </>
            )}

            <div className="drawer__label">Навигация</div>
            {NAV.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => "drawer__item" + (isActive ? " drawer__item--active" : "")}
              >
                {({ isActive }) => (
                  <>
                    <span className={"drawer__dot" + (isActive ? "" : " drawer__dot--off")} />
                    {label}
                  </>
                )}
              </NavLink>
            ))}

            {projectId && (
              <>
                <div className="drawer__label">Текущий проект</div>
                {PROJECT_MODES.map(([suffix, label]) => (
                  <NavLink
                    key={suffix}
                    to={`/projects/${projectId}${suffix}`}
                    end
                    className={({ isActive }) => "drawer__item" + (isActive ? " drawer__item--active" : "")}
                  >
                    {label}
                  </NavLink>
                ))}
              </>
            )}

            <div className="menu__div" />
            <button type="button" className="drawer__item" onClick={() => setTheme(toggleTheme())}>
              <span style={{ marginRight: 10 }}>{theme === "dark" ? "☀" : "☾"}</span>
              Тема: {themeLabel}
            </button>

            {user && (
              <div className="drawer__user">
                <div className="user-avatar user-avatar--lg">{initials(user.full_name || user.email)}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {user.full_name && <div className="menu__uname">{user.full_name}</div>}
                  <div className="menu__umail">{user.email}</div>
                </div>
              </div>
            )}
            <button type="button" className="drawer__exit" onClick={doLogout}>
              Выйти
            </button>
          </div>
        </>
      )}

      <Modal
        open={createOpen}
        onClose={() => !creating && setCreateOpen(false)}
        title="Создать организацию"
        sub="Новая организация получит отдельные проекты, участников и тариф. Вы станете её владельцем."
        actions={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)} disabled={creating}>
              Отмена
            </Button>
            <Button onClick={submitCreateOrg} loading={creating} disabled={!newOrgName.trim()}>
              Создать
            </Button>
          </>
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submitCreateOrg();
          }}
        >
          <Field
            label="Название организации"
            placeholder="ООО «Ваша компания»"
            value={newOrgName}
            autoFocus
            disabled={creating}
            onChange={(e) => setNewOrgName(e.target.value)}
          />
        </form>
      </Modal>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
