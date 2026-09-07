import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

/**
 * Дымовые сквозные тесты: приложение целиком — браузер, фронт, бэкенд, база.
 *
 * Юнит-тестов в проекте больше полутора тысяч, но каждый проверяет свой слой. Швы
 * между слоями — вход → организация → проект/дело → расчёт → документ — не покрыты
 * ничем: переименованный маршрут, сломанный ленивый чанк или разъехавшийся контракт
 * не уронят ни один из них. Здесь проверяется **только проходимость** этих швов, а не
 * содержание экранов: методику стерегут свои тесты, дублировать её тут незачем.
 *
 * Оба сервера поднимает сам Playwright. База — отдельный файл SQLite на прогон
 * (`E2E_DB`), чтобы e2e не трогал ни dev-базу, ни чужие данные.
 */
const PORT = Number(process.env.E2E_PORT ?? 5273);
const API_PORT = Number(process.env.E2E_API_PORT ?? 8123);
const DB = process.env.E2E_DB ?? "/tmp/finans-e2e.db";

/** Предустановленный Chromium образа (если есть) — иначе браузер ставит Playwright. */
const PREINSTALLED = [
  process.env.E2E_CHROMIUM,
  "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
].find((p): p is string => !!p && existsSync(p));

export default defineConfig({
  testDir: "./e2e",
  // Прогон дымовой: параллелить нечего, а общая база на два воркера дала бы гонки.
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // Скриншот и трасса — только у падения: разбирать сквозной тест по логам
    // бесполезно, а хранить артефакты зелёных прогонов незачем.
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
    launchOptions: {
      args: ["--no-sandbox", "--disable-gpu"],
      // Готовый Chromium из образа, если его ревизия не совпала с ожидаемой этой
      // версией Playwright. Обычная установка (`npx playwright install chromium`, как
      // в CI) кладёт свой браузер — тогда путь не подставляется и берётся он.
      ...(PREINSTALLED ? { executablePath: PREINSTALLED } : {}),
    },
  },
  webServer: [
    {
      command:
        `python -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT} --log-level warning`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: { DATABASE_URL: `sqlite:///${DB}`, APP_ENV: "development" },
    },
    {
      command: `npx vite --port ${PORT} --strictPort`,
      url: `http://127.0.0.1:${PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      // Фронт ходит в API через прокси vite; в e2e он смотрит на свой бэкенд.
      env: { E2E_API_PORT: String(API_PORT) },
    },
  ],
});
