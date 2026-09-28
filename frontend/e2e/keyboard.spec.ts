import { expect, test, type Page } from "@playwright/test";

/**
 * Клавиатура (пакет H, H6): продуктом можно пользоваться без мыши.
 *
 * Проверяются **ходы человека**, а не разметка: разметку стережёт `axe-core` в матрице
 * скриншотов, а он не видит, куда уходит фокус после нажатия. Три шва: вход табуляцией
 * и Enter; меню шапки открывается с клавиатуры и закрывается Esc с возвратом фокуса;
 * модалка держит фокус внутри себя, не отнимает его у поля, в котором печатают, и после
 * Esc возвращает на кнопку, которая её открыла.
 *
 * Чтение с экрана автоматикой не проверяется — это напечатано рядом с отметкой P13.
 */

const stamp = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const PASSWORD = "keyboard-pass-123";

async function register(page: Page): Promise<string> {
  const email = `e2e-keys-${stamp()}@example.test`;
  await page.addInitScript(() => localStorage.setItem("fe_product", "business"));
  await page.goto("/register");
  await page.getByLabel("ФИО").fill("Клавиатурный Тест");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Пароль").fill(PASSWORD);
  await page.getByLabel("Название организации").fill("ООО «Клавиши»");
  await page.getByRole("button", { name: /Создать аккаунт/ }).click();
  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();
  return email;
}

/** Что сейчас в фокусе — словами, по которым человек узнаёт элемент. */
async function focused(page: Page): Promise<string> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return "(ничего)";
    const label = el.id ? document.querySelector(`label[for="${el.id}"]`)?.textContent : null;
    const wrap = el.closest("label")?.textContent;   // флажок внутри своей подписи
    const name = (el.getAttribute("aria-label") ?? label ?? wrap ?? el.textContent ?? "").trim();
    return `${name} [${el.tagName.toLowerCase()}${el.className ? "." + String(el.className).split(" ")[0] : ""}]`;
  });
}

/**
 * Видно, где фокус: у элемента в фокусе или у его рамки (поле рисует кольцо на обёртке
 * через `:focus-within`) меняется контур, тень или граница. Сравнивается с тем же
 * элементом без фокуса — тень карточки, которая есть всегда, индикатором не считается.
 * Переходы на время замера выключены: кольцо поля появляется за 0,14 с, и замер сразу
 * после нажатия попадал в начало перехода — «кольца нет» там, где оно есть.
 */
async function focusVisible(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    if (!document.getElementById("kb-no-motion")) {
      const style = document.createElement("style");
      style.id = "kb-no-motion";
      style.textContent = "*, *::before, *::after { transition: none !important; animation: none !important; }";
      document.head.appendChild(style);
    }
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return false;
    const look = () => {
      const parts: string[] = [];
      for (let a: HTMLElement | null = el, i = 0; a && i < 3; a = a.parentElement, i++) {
        const cs = getComputedStyle(a);
        parts.push(`${cs.outlineStyle} ${cs.outlineWidth} ${cs.outlineColor}|${cs.boxShadow}|${cs.borderColor}`);
      }
      return parts.join(" / ");
    };
    const withFocus = look();
    el.blur();
    const without = look();
    el.focus();
    return withFocus !== without;
  });
}

test("вход — табуляцией и Enter, фокус виден на каждой остановке", async ({ page }) => {
  const email = await register(page);
  await page.evaluate(() => localStorage.removeItem("fe_token"));
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Войти" })).toBeVisible();

  const stops: string[] = [];
  for (let i = 0; i < 20 && !stops.some((x) => x.startsWith("Войти")); i++) {
    await page.keyboard.press("Tab");
    const name = await focused(page);
    stops.push(name);
    expect(await focusVisible(page), `фокус на «${name}» не виден (путь: ${stops.join(" → ")})`)
      .toBe(true);
  }
  // Каждое поле — одна остановка: поле, пересоздаваемое при смене ошибки, давало две,
  // и Tab из адреса уводил не в пароль, а в новую копию адреса.
  expect(new Set(stops).size, `остановки повторяются: ${stops.join(" → ")}`).toBe(stops.length);
  // Порядок — порядок чтения формы: адрес, пароль, «запомнить», кнопка.
  const at = (s: string) => stops.findIndex((x) => x.startsWith(s));
  expect(at("Email")).toBeGreaterThanOrEqual(0);
  expect(at("Email")).toBeLessThan(at("Пароль"));
  expect(at("Пароль")).toBeLessThan(at("Запомнить"));
  expect(at("Запомнить")).toBeLessThan(at("Войти"));

  // Сама форма — без мыши: поле за полем и Enter.
  await page.getByLabel("Email").focus();
  await page.keyboard.type(email);
  await page.keyboard.press("Tab");
  await page.keyboard.type(PASSWORD);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();
});

test("меню шапки: Enter открывает, Esc закрывает и возвращает фокус", async ({ page }) => {
  await register(page);
  const trigger = page.locator(".shell-userbtn");
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("button", { name: /Выйти/ })).toBeVisible();

  // Фокус в меню — и Esc оттуда: человек ушёл табуляцией вглубь и передумал.
  await page.keyboard.press("Tab");
  await page.keyboard.press("Escape");
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(trigger).toBeFocused();
});

test("модалка: фокус внутри, печать не прерывается, Esc возвращает на кнопку", async ({ page }) => {
  await register(page);
  await page.goto("/organization?tab=members");
  const opener = page.getByRole("button", { name: /Пригласить участника/ });
  await opener.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Пригласить участника" });
  await expect(dialog).toBeVisible();

  // Поле по подписи — у поля есть имя.
  const emailInput = dialog.getByLabel("Email");
  await emailInput.focus();
  // Посимвольно, как человек: каждое нажатие перерисовывает страницу-владельца, и
  // модалка, отнимающая фокус при перерисовке, оставила бы в поле одну букву.
  await page.keyboard.type("ivan@example.test", { delay: 15 });
  await expect(emailInput).toHaveValue("ivan@example.test");
  await expect(emailInput).toBeFocused();

  // Табуляция не уходит за модалку на страницу под затемнением.
  for (let i = 0; i < 25; i++) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate((d) => d.contains(document.activeElement)),
           `после ${i + 1} нажатий Tab фокус ушёл из модалки`).toBe(true);
  }
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
});
