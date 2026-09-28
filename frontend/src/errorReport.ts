import { api } from "./api/client";
import { getCapabilities } from "./api/auth";

/**
 * Ошибки интерфейса — в трекер платформы (пакет G, G7).
 *
 * Через свой маршрут сервера (`/client-errors`), а не прямо в трекер: адрес трекера не
 * попадает в сборку, вычистка одна — серверная. Отправляется **только там, где трекер
 * включён** (`/auth/capabilities`): без него ошибки никуда не уходят, и лишних запросов
 * нет. Что уходит: сообщение, стек и **путь без строки запроса** (в ней ходят токены
 * ссылок) — ни содержимого экрана, ни введённых чисел.
 *
 * Предел — несколько ошибок за загрузку страницы, повтор той же не уходит: зациклившийся
 * рендер иначе засыпал бы трекер одинаковыми событиями. Отправка ошибки **никогда не
 * бросает** — ошибка отчёта об ошибке рождала бы новую.
 */

/** Сколько разных ошибок отправить за одну загрузку страницы. */
export const MAX_REPORTS_PER_LOAD = 5;

let sent = 0;
const seen = new Set<string>();
let enabled: Promise<boolean> | null = null;

function trackerEnabled(): Promise<boolean> {
  enabled ??= getCapabilities().then((c) => Boolean(c.error_tracking)).catch(() => false);
  return enabled;
}

export async function reportClientError(error: unknown): Promise<void> {
  try {
    const err = error instanceof Error ? error : new Error(String(error));
    const message = `${err.name}: ${err.message}`.slice(0, 500);
    if (sent >= MAX_REPORTS_PER_LOAD || seen.has(message)) return;
    seen.add(message);
    sent += 1;
    if (!(await trackerEnabled())) return;
    await api.post("/api/v1/client-errors", {
      message,
      stack: (err.stack ?? "").slice(0, 4000),
      path: window.location.pathname.slice(0, 300),
      release: String(import.meta.env.MODE ?? "").slice(0, 40),
    });
  } catch {
    // Отчёт об ошибке не должен рождать новую ошибку.
  }
}

/** Ловить и то, что пролетело мимо границы ошибок React: обработчики событий, промисы. */
export function installGlobalErrorReporting(): void {
  window.addEventListener("error", (e) => { void reportClientError(e.error ?? e.message); });
  window.addEventListener("unhandledrejection",
                          (e) => { void reportClientError(e.reason); });
}

/** Только для тестов: предел и кеш — на загрузку страницы, а тест — не загрузка. */
export function resetErrorReportingForTests(): void {
  sent = 0;
  seen.clear();
  enabled = null;
}
