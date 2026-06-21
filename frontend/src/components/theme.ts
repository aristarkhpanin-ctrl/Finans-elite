const KEY = "fe_theme";
export type Theme = "light" | "dark";

export function getTheme(): Theme {
  return (localStorage.getItem(KEY) as Theme) || "light";
}

export function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(KEY, theme);
}

export function toggleTheme(): Theme {
  const next: Theme = getTheme() === "dark" ? "light" : "dark";
  applyTheme(next);
  return next;
}
