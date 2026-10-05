import AxeBuilder from "@axe-core/playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

/**
 * Экранный диктор — автоматическое приближение (пакет K, K5).
 *
 * Настоящий диктор (NVDA, VoiceOver) этим тестом не заменён — это работа человека, и она
 * названа под таблицей P13. Здесь проверяется то, без чего диктору не на что опереться,
 * и что автоматика умеет увидеть:
 *
 * - **переход называет себя**: у каждой страницы свой заголовок документа, а живая
 *   область объявляет новую страницу — в одностраничном приложении переход иначе
 *   беззвучен;
 * - **шапку можно обойти**: первая остановка табуляции — «Перейти к содержимому», и она
 *   ведёт в `main`;
 * - **ориентиры и заголовки** — правила `axe-core` из «лучших практик», которых нет в
 *   наборе WCAG A/AA матрицы: один `main`, один `h1`, порядок заголовков, всё содержимое
 *   внутри ориентиров;
 * - с `SCREENS=1` — **снимки дерева доступности** (`screens/aria/*.yml`): то, что диктор
 *   получает вместо экрана, для чтения глазами.
 */

const stamp = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const ARIA_OUT = "screens/aria";

/** Правила «лучших практик» об ориентирах и заголовках — то, по чему ходит диктор. */
const STRUCTURE_RULES = [
  "document-title", "page-has-heading-one", "landmark-one-main", "region", "heading-order",
  "landmark-unique", "landmark-no-duplicate-main", "landmark-main-is-top-level", "bypass",
  "empty-heading",
];

async function register(page: Page, product: "business" | "audit"): Promise<void> {
  await page.addInitScript((p) => localStorage.setItem("fe_product", p), product);
  await page.goto("/register");
  await page.getByLabel("ФИО").fill("Диктор Тест");
  await page.getByLabel("Email").fill(`e2e-sr-${stamp()}@example.test`);
  await page.getByLabel("Пароль").fill("reader-pass-123");
  await page.getByLabel("Название организации").fill("ООО «Слух»");
  // Согласие на обработку ПД — отдельной отметкой (L5): без неё регистрации нет.
  await page.getByRole("checkbox", { name: /согласие на обработку/ }).check();
  await page.getByRole("button", { name: /Создать аккаунт/ }).click();
  await expect(page.getByRole("heading", { name: product === "audit" ? "Дела" : "Проекты" }))
    .toBeVisible();
}

/** Объявление живой области после перехода (с паузой объявителя). */
async function announced(page: Page, title: RegExp): Promise<void> {
  await expect(page.getByTestId("route-announcer")).toHaveText(title, { timeout: 5_000 });
}

/**
 * Структура страницы: правила `axe-core` об ориентирах и заголовках, ровно один h1 и — по
 * дереву доступности, то есть по тому, что диктор действительно получит, — ни одной кнопки
 * или ссылки с именем из одних значков. `axe` такое пропускает: имя «☾» или «?» у него
 * есть, а слов в нём нет (так звались кнопка темы и все подсказки полей до K5).
 */
async function structure(page: Page, name: string, minH2 = 0): Promise<string[]> {
  const problems: string[] = [];
  const h1 = await page.locator("h1").count();
  if (h1 !== 1) problems.push(`${name}: h1 — ${h1}, а не один`);
  const h2 = await page.getByRole("heading", { level: 2 }).count();
  if (h2 < minH2) problems.push(`${name}: заголовков разделов (h2) — ${h2}, нужно не меньше ${minH2}`);
  const result = await new AxeBuilder({ page }).withRules(STRUCTURE_RULES).analyze();
  for (const v of result.violations) {
    for (const node of v.nodes) problems.push(`${name}: ${v.id} — ${node.target.join(" ")}`);
  }
  const tree = await page.locator("body").ariaSnapshot();
  for (const m of tree.matchAll(/- (button|link) "([^"]*)"/g)) {
    if (!/[\p{L}\d]/u.test(m[2])) problems.push(`${name}: ${m[1]} без слов в имени — «${m[2]}»`);
  }
  if (process.env.SCREENS) {
    mkdirSync(ARIA_OUT, { recursive: true });
    writeFileSync(`${ARIA_OUT}/${name}.yml`, tree);
  }
  return problems;
}

test("«Финанс-Элит»: переходы называют себя, структура страниц", async ({ page }) => {
  const problems: string[] = [];
  await page.goto("/login");
  await expect(page).toHaveTitle("Вход — Финанс-Элит");
  problems.push(...await structure(page, "login"));

  await register(page, "business");
  await expect(page).toHaveTitle("Проекты — Финанс-Элит");
  problems.push(...await structure(page, "projects"));

  await page.getByRole("button", { name: /Производство \(демо\)/ }).first().click();
  await page.getByRole("button", { name: "Создать проект" }).click();
  await page.getByRole("button", { name: /Открыть редактор/ }).click();
  await expect(page).toHaveTitle(/^Редактор — .+ — Финанс-Элит$/);
  await announced(page, /^Открыта страница: Редактор — /);
  problems.push(...await structure(page, "editor", 4));

  await page.getByRole("button", { name: /Рассчитать/ }).click();
  await expect(page.getByText(/NPV/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page).toHaveTitle(/^Результаты — .+ — Финанс-Элит$/);
  await announced(page, /^Открыта страница: Результаты — /);
  problems.push(...await structure(page, "results", 3));

  await page.getByRole("button", { name: "← Редактор" }).click();
  await page.getByRole("button", { name: "Анализ" }).click();
  await expect(page).toHaveTitle(/^Анализ — .+ — Финанс-Элит$/);
  problems.push(...await structure(page, "analysis", 1));

  for (const [link, title, name] of [
    ["Холдинги", "Холдинги — Финанс-Элит", "holdings"],
    ["Организация", "Организация — Финанс-Элит", "organization"],
  ] as const) {
    await page.getByRole("link", { name: link }).first().click();
    await expect(page).toHaveTitle(title);
    await announced(page, new RegExp(`^Открыта страница: ${title}$`));
    problems.push(...await structure(page, name));
  }
  expect(problems, "структура для диктора").toEqual([]);
});

test("«Финанс-Аудит»: заголовок дела и структура", async ({ page }) => {
  const problems: string[] = [];
  await register(page, "audit");
  await expect(page).toHaveTitle("Дела — Финанс-Аудит");
  problems.push(...await structure(page, "audit-home"));

  await page.getByRole("button", { name: /Посмотреть демо-дело/ }).click();
  await expect(page.getByRole("button", { name: "Сводка" })).toBeVisible();
  await expect(page).toHaveTitle(/^Дело — .+ — Финанс-Аудит$/);
  await announced(page, /^Открыта страница: Дело — /);
  problems.push(...await structure(page, "audit-case"));
  expect(problems, "структура для диктора").toEqual([]);
});

test("шапку можно обойти: первая остановка — «Перейти к содержимому»", async ({ page }) => {
  await register(page, "business");
  await page.locator("body").focus();
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Перейти к содержимому" });
  await expect(skip).toBeFocused();
  const box = await skip.boundingBox();
  expect(box && box.y >= 0, "ссылка видна в фокусе").toBe(true);
  await page.keyboard.press("Enter");
  await expect(page.locator("main#content")).toBeFocused();
  // Следующая остановка — уже внутри содержимого, а не снова в шапке.
  await page.keyboard.press("Tab");
  const inMain = await page.evaluate(() => !!document.activeElement?.closest("main"));
  expect(inMain, "после обхода Tab ведёт в содержимое").toBe(true);
});
