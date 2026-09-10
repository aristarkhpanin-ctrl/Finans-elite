import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

/**
 * Служебный контур не спрашивает содержимого моделей клиента (правило 6 плана B1).
 *
 * Экранный тест на это не годится: он проверял бы, что мы не нарисовали то, чего нам не
 * присылали. Проверять надо **запросы** — они и есть граница. Сервер держит ту же
 * границу со своей стороны (`tests/test_admin_staff.py`), и оба обещания независимы:
 * ослабнет одно — второе не промолчит.
 */

const source = readFileSync(
  fileURLToPath(new URL("./admin.ts", import.meta.url)), "utf8");

const urls = [...source.matchAll(/["'`](\/api\/v1\/[^"'`$]*)/g)].map((m) => m[1]);

it("ходит только в служебный контур", () => {
  expect(urls.length).toBeGreaterThan(0);
  for (const url of urls) expect(url.startsWith("/api/v1/admin")).toBe(true);
});

it("не запрашивает ни проектов, ни дел клиента", () => {
  // Метаданные — да (организации, пользователи, журнал), содержимое — нет. Появившийся
  // здесь запрос за моделью означал бы, что владелец SaaS читает финансовые модели
  // своих клиентов: ровно то, чего клиент и опасается.
  for (const url of urls) {
    expect(/\/projects|\/audit\/subjects|\/audit\/groups|business-plan|report\.docx/
      .test(url)).toBe(false);
  }
});
