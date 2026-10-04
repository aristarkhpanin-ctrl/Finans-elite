import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

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

async function register(page: Page, product: "business" | "audit" = "business"): Promise<string> {
  const email = `e2e-keys-${stamp()}@example.test`;
  await page.addInitScript((p) => localStorage.setItem("fe_product", p), product);
  await page.goto("/register");
  await page.getByLabel("ФИО").fill("Клавиатурный Тест");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Пароль").fill(PASSWORD);
  await page.getByLabel("Название организации").fill("ООО «Клавиши»");
  await page.getByRole("button", { name: /Создать аккаунт/ }).click();
  await expect(page.getByRole("heading", { name: product === "audit" ? "Дела" : "Проекты" }))
    .toBeVisible();
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

async function authHeaders(page: Page): Promise<Record<string, string>> {
  const [token, org] = await page.evaluate(
    () => [localStorage.getItem("fe_token"), localStorage.getItem("fe_org")]);
  return { Authorization: `Bearer ${token}`, "X-Organization-Id": org ?? "" };
}

/** Проект из шаблона, посчитанный: у результатов и анализа должно быть что показать. */
async function project(api: APIRequestContext, headers: Record<string, string>): Promise<string> {
  const model = await (await api.get("/api/v1/templates/production", { headers })).json();
  const { id } = await (await api.post("/api/v1/projects",
    { headers, data: { name: "Клавиатурный проект", model } })).json();
  expect((await api.post(`/api/v1/projects/${id}/calculate`, { headers })).ok()).toBeTruthy();
  return id;
}

/** Нажимать Tab, пока фокус не встанет на элемент; сколько нажатий — столько и надо. */
async function tabTo(page: Page, target: ReturnType<Page["locator"]>, limit = 60): Promise<number> {
  for (let i = 1; i <= limit; i++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((el) => el === document.activeElement)) return i;
  }
  throw new Error(`за ${limit} нажатий Tab фокус до элемента не дошёл`);
}

test("редактор: вкладка, поле и сохранение — без мыши", async ({ page }) => {
  await register(page);
  const id = await project(page.request, await authHeaders(page));
  await page.goto(`/projects/${id}`);
  const sales = page.getByRole("button", { name: /^Сбыт/ });
  await tabTo(page, sales);
  await page.keyboard.press("Enter");
  // Выбранная вкладка названа не только цветом: диктор слышит «нажата».
  await expect(sales).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: /^Проект/ }).first()).toHaveAttribute("aria-pressed", "false");

  await page.getByRole("button", { name: /^Проект/ }).first().focus();
  await page.keyboard.press("Enter");
  const loss = page.getByLabel("Налоговый убыток на старте");
  await tabTo(page, loss, 120);
  await page.keyboard.type("1000");
  const saveBtn = page.getByRole("button", { name: "Сохранить" });
  await tabTo(page, saveBtn, 200);
  await page.keyboard.press("Enter");
  await expect(page.getByText("Все изменения сохранены")).toBeVisible();
});

test("результаты и анализ: отчёт, период и расчёт — с клавиатуры", async ({ page }) => {
  await register(page);
  const id = await project(page.request, await authHeaders(page));
  await page.goto(`/projects/${id}/results`);
  const cash = page.getByRole("button", { name: "Кэш-фло", exact: true }).first();
  await expect(cash).toBeVisible({ timeout: 30_000 });
  await tabTo(page, cash);
  await page.keyboard.press("Enter");
  await expect(cash).toHaveAttribute("aria-pressed", "true");
  const quarter = page.getByRole("button", { name: "Квартал" });
  await tabTo(page, quarter);
  await page.keyboard.press("Enter");
  await expect(quarter).toHaveAttribute("aria-pressed", "true");

  await page.goto(`/projects/${id}/analysis`);
  const sens = page.getByRole("button", { name: /Чувствительность/ }).first();
  await tabTo(page, sens);
  await page.keyboard.press("Enter");
  // Коэффициенты: была <div onClick> — с клавиатуры не открывалась вовсе (H6).
  const factors = page.getByRole("button", { name: /^Коэффициенты/ });
  await tabTo(page, factors);
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Коэффициенты")).toBeFocused();
  await page.keyboard.press("Enter");                  // закрыть правку тем же ключом
  const calc = page.getByRole("button", { name: "Рассчитать" });
  await tabTo(page, calc);
  await page.keyboard.press("Enter");
  await expect(page.getByText("NPV в зависимости от коэффициента")).toBeVisible({ timeout: 60_000 });
});

test("телефон: выдвижная панель — фокус внутри, Esc возвращает на кнопку", async ({ page }) => {
  await page.setViewportSize({ width: 402, height: 874 });
  await register(page);
  const burger = page.getByRole("button", { name: "Меню" });
  await burger.focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog", { name: "Меню" });
  await expect(drawer).toBeVisible();
  // Панель — диалог: фокус уходит в неё и табуляцией из неё не выходит.
  expect(await drawer.evaluate((d) => d.contains(document.activeElement))).toBe(true);
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press("Tab");
    expect(await drawer.evaluate((d) => d.contains(document.activeElement)),
           `после ${i + 1} нажатий Tab фокус ушёл из панели`).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(burger).toBeFocused();
});

test("список проектов: вид и открытие проекта — с клавиатуры", async ({ page }) => {
  await register(page);
  await project(page.request, await authHeaders(page));
  await page.goto("/projects");
  const rows = page.getByRole("button", { name: "Список" });
  await tabTo(page, rows);
  await page.keyboard.press("Enter");
  await expect(rows).toHaveAttribute("aria-pressed", "true");
  const open = page.getByRole("button", { name: "Клавиатурный проект" }).first();
  await tabTo(page, open);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/projects\/[^/]+$/);
});

test("план-факт и печать: вкладка, режим печати и возврат — фокус не теряется", async ({ page }) => {
  await register(page);
  const headers = await authHeaders(page);
  const model = await (await page.request.get("/api/v1/templates/production", { headers })).json();
  model.actualization = { actual_until: 1, actuals: { C1: ["1000", "2000"] } };
  const { id } = await (await page.request.post("/api/v1/projects",
    { headers, data: { name: "План-факт с клавиатуры", model } })).json();
  await page.goto(`/projects/${id}/results`);
  const pf = page.getByRole("button", { name: "План-факт", exact: true });
  await expect(pf).toBeVisible({ timeout: 30_000 });
  await tabTo(page, pf);
  await page.keyboard.press("Enter");
  await expect(pf).toHaveAttribute("aria-pressed", "true");

  // Режим печати прячет кнопку, которая его открыла: фокус обязан уйти на панель печати,
  // иначе он падает в никуда и следующий Tab начинается с начала страницы.
  const printBtn = page.locator(".screen-only").getByRole("button", { name: "Печать" });
  await tabTo(page, printBtn, 120);
  await page.keyboard.press("Enter");
  const back = page.getByRole("button", { name: /К результатам/ });
  await expect(back).toBeVisible();
  await expect(back).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(printBtn).toBeFocused();
  // Esc выходит из режима печати, как из модалки, — и тоже возвращает на кнопку.
  await page.keyboard.press("Enter");
  await expect(back).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(back).toBeHidden();
  await expect(printBtn).toBeFocused();
});

test("холдинг: создание, участник и свод — без мыши", async ({ page }) => {
  await register(page);
  await project(page.request, await authHeaders(page));
  await page.goto("/holdings");
  const name = page.getByLabel("Название холдинга");
  await tabTo(page, name);
  await page.keyboard.type("Клавиатурная группа");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/holdings\/[^/]+$/);

  const add = page.getByRole("button", { name: /Добавить проект/ }).first();
  await tabTo(page, add);
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Добавить проект в холдинг" });
  await expect(dialog).toBeVisible();
  const pick = dialog.getByLabel("Проект");
  await pick.focus();
  await page.keyboard.press("ArrowDown");
  const confirm = dialog.getByRole("button", { name: "Добавить" });
  await tabTo(page, confirm, 10);
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();

  const run = page.getByRole("button", { name: /Консолидировать/ });
  await tabTo(page, run);
  await page.keyboard.press("Enter");
  await expect(page.getByText("Сводный NPV")).toBeVisible({ timeout: 30_000 });
});

test("дело «Аудита»: открыть из списка, раздел и вкладка — с клавиатуры", async ({ page }) => {
  await register(page, "audit");
  const headers = await authHeaders(page);
  expect((await page.request.post("/api/v1/audit/subjects/demo", { headers })).ok()).toBeTruthy();
  await page.goto("/audit");
  const open = page.getByRole("button", { name: /Торговый дом/ }).first();
  await tabTo(page, open);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/audit\/[^/]+$/);

  const health = page.getByRole("button", { name: "Финансовое состояние" });
  await tabTo(page, health, 80);
  await page.keyboard.press("Enter");
  await expect(health).toHaveAttribute("aria-pressed", "true");
  const diag = page.getByRole("tab", { name: /Диагностика/ });
  await tabTo(page, diag);
  await page.keyboard.press("Enter");
  await expect(diag).toHaveAttribute("aria-selected", "true");
});
