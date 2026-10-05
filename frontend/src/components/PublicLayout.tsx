import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { CubeHero } from "./CubeHero";
import { applyProduct, PRODUCTS } from "./product";
import { getTheme, toggleTheme } from "./theme";

/**
 * Каркас публичных страниц (пакет L, L5): главная, тарифы, документы. Видны **без входа** —
 * их читают до регистрации, и их проверяет платёжный агрегатор. Подвал со ссылками на
 * документы — на каждой странице: оферта, политика и реквизиты, которые надо искать, для
 * проверяющего не существуют.
 */

/** Документы в подвале — одним перечнем и здесь, и на экранах входа. */
export const LEGAL_NAV: [string, string][] = [
  ["/legal/offer", "Оферта"],
  ["/legal/privacy", "Политика обработки ПД"],
  ["/legal/consent", "Согласие на обработку ПД"],
  ["/legal/requisites", "Реквизиты"],
];

export function PublicLayout({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState(getTheme());
  // Публичные страницы — витрина «Финанс-Элит»; память о продукте посетителя не трогаем.
  useEffect(() => applyProduct("business", false), []);
  const product = PRODUCTS.business;
  return (
    <div className="app pub">
      <header className="shell-header pub-head">
        <Link to="/" className="shell-brand" style={{ textDecoration: "none" }}>
          <div className="shell-mark">
            <CubeHero accent={product.cubeAccent} backdrop="transparent" showEnvironment={false}
                      showOrbit={false} pointerTilt={false} />
          </div>
          <span className="shell-word">Финанс<span>{product.brand}</span></span>
        </Link>
        <nav className="pub-nav" aria-label="Разделы сайта">
          <NavLink to="/pricing" className={({ isActive }) =>
            "pub-nav__item" + (isActive ? " pub-nav__item--active" : "")}>Тарифы</NavLink>
          <NavLink to="/legal" className={({ isActive }) =>
            "pub-nav__item" + (isActive ? " pub-nav__item--active" : "")}>Документы</NavLink>
          <Link to="/login" className="btn btn--ghost pub-nav__btn">Войти</Link>
          <Link to="/register" className="btn pub-nav__btn">Регистрация</Link>
        </nav>
        {/* Тема — отдельно от навигации: на телефоне она встаёт в строку марки, а разделы
            сайта — одной строкой ниже, вместо трёх рваных строк шапки. */}
        <button
          type="button"
          className="icon-btn38 pub-theme"
          aria-label={theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему"}
          onClick={() => setTheme(toggleTheme())}
        >
          <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
        </button>
      </header>
      <main className="content" id="content" tabIndex={-1}>{children}</main>
      <footer className="pub-foot">
        <nav className="pub-foot__links" aria-label="Документы">
          {LEGAL_NAV.map(([to, label]) => <Link key={to} to={to}>{label}</Link>)}
        </nav>
        <div className="pub-foot__note">
          Финанс-Элит и Финанс-Аудит — сервисы финансового моделирования и анализа
          отчётности. Расчёты — инструмент, а не инвестиционная рекомендация.
        </div>
      </footer>
    </div>
  );
}
