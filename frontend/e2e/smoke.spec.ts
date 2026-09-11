import { expect, test, type Page } from "@playwright/test";

/**
 * Дымовой проход по обоим продуктам: регистрация → рабочая область → сущность →
 * расчёт → результат на экране.
 *
 * Проверяется **проходимость швов**, а не содержание экранов. Всё, что здесь
 * утверждается о числах, — минимум, доказывающий, что расчёт действительно дошёл до
 * браузера: методику стерегут свои тесты, и повторять её тут значило бы завести
 * вторую, медленную и хрупкую копию.
 */

/** Почта на прогон: база живёт между запусками, повтор упёрся бы в «email занят». */
const stamp = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

async function register(page: Page, product: "business" | "audit"): Promise<string> {
  const email = `e2e-${product}-${stamp()}@example.test`;
  // Продукт выбирается до входа: у «/register» своего продукта нет, берётся последний.
  await page.addInitScript((p) => localStorage.setItem("fe_product", p), product);
  await page.goto("/register");
  await page.getByLabel("ФИО").fill("Дымовой Тест");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Пароль").fill("smoke-pass-123");
  await page.getByLabel("Название организации").fill("ООО «Дымовая»");
  await page.getByRole("button", { name: /Создать аккаунт/ }).click();
  return email;
}

test("«Финанс-Элит»: регистрация → проект → расчёт → отчёты", async ({ page }) => {
  await register(page, "business");

  // После регистрации приложение открывает продукт, из которого пришли.
  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();

  // Проект заводится из шаблона — так же, как начинает пользователь: у шаблона есть
  // модель, и расчёту будет что считать.
  await page.getByRole("button", { name: /Производство \(демо\)/ }).first().click();
  // Сначала шаблон говорит о себе: числа в нём выдуманы (D4). Проверяем сам шов —
  // без оговорки человек построил бы модель на чужих числах, не узнав об этом.
  await expect(page.getByText(/не отраслевая норма/)).toBeVisible();
  await page.getByRole("button", { name: "Создать проект" }).click();
  // Созданный проект предлагает открыть редактор — идём тем же путём, что человек.
  await page.getByRole("button", { name: /Открыть редактор/ }).click();

  // Редактор модели открылся — значит маршрут проекта и загрузка модели работают.
  const calc = page.getByRole("button", { name: /Рассчитать/ });
  await expect(calc).toBeVisible();
  await calc.click();

  // Результаты — отдельная лениво загружаемая страница: её чанк тоже проверяется.
  await expect(page.getByText(/NPV/).first()).toBeVisible({ timeout: 30_000 });
});

test("«Финанс-Аудит»: регистрация → дело → отчётность → вердикт и версия", async ({ page }) => {
  await register(page, "audit");
  await expect(page.getByRole("heading", { name: "Дела" })).toBeVisible();

  // Демо-дело — обычное дело с готовой отчётностью: даёт ввод, не набивая цифры руками.
  await page.getByRole("button", { name: /Посмотреть демо-дело/ }).click();

  // Открылась карточка дела: сводка считается на бэкенде и приезжает на экран.
  await expect(page.getByRole("button", { name: "Сводка" })).toBeVisible();
  await expect(page.getByText(/Охват проверки|Вердикт|Отчётность/).first()).toBeVisible();

  // Отчёты — аналитическая форма из ответа `/analyze`.
  await page.getByRole("button", { name: "Отчётность" }).click();
  // Внутри раздела вкладки — это `role="tab"`, а не кнопки разделов.
  await page.getByRole("tab", { name: "Отчёты" }).click();
  await expect(page.getByText("Выручка").first()).toBeVisible();

  // Версия дела: снимок проходит через новую таблицу и возвращается в список.
  await page.getByRole("button", { name: "Версии" }).click();
  await page.getByLabel("Название версии").fill("Дымовая версия");
  await page.getByRole("button", { name: "Сохранить версию" }).click();
  await expect(page.getByText("Дымовая версия")).toBeVisible();
});

test("выход возвращает на вход того же продукта", async ({ page }) => {
  // Шов, который не виден ни одному юнит-тесту: продукт переживает выход.
  await register(page, "audit");
  await expect(page.getByRole("heading", { name: "Дела" })).toBeVisible();

  await page.getByRole("button", { name: /example\.test/ }).click();
  await page.getByRole("button", { name: "Выйти" }).click();

  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText("Финанс-Аудит").first()).toBeVisible();
});
