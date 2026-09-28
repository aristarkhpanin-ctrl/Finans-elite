import { mkdirSync, writeFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page, type Route } from "@playwright/test";

/**
 * Матрица скриншотов P13 (пакет G, G15): экраны «Элиты» × светлая/тёмная тема ×
 * 1240 / 864 / 402 px. Не дым и не регрессия — снимки **для человека**, который смотрит
 * на них глазами: в P13 отмечается только то, что действительно просмотрено.
 *
 * Запускается отдельно — `npm run screens`: полторы сотни полностраничных снимков
 * съедают минуты, а обычному `npm run e2e` (он в CI) нечего с ними делать. Без
 * `SCREENS=1` спецификация пропускается целиком.
 *
 * Выход — `screens/` (в .gitignore): PNG и `index.html`-галерея (экран — строка, шесть
 * вариантов рядом). Данные для экранов заводятся запросами к API тем же входом, что у
 * браузера: проект из шаблона с расчётом, второй проект, холдинг, месяцы факта, — чтобы
 * экраны были не пустыми заглушками.
 */
test.skip(process.env.SCREENS !== "1", "матрица скриншотов — отдельной командой: npm run screens");
test.setTimeout(30 * 60_000);

const OUT = "screens";
const WIDTHS = [["desktop", 1240, 900], ["tablet", 864, 1000], ["mobile", 402, 874]] as const;
const THEMES = ["light", "dark"] as const;
/** Полностраничный снимок обрезается: редактор длиннее десяти экранов, а смотрят верх. */
const MAX_HEIGHT = 3200;

type Width = (typeof WIDTHS)[number][0];
/** Страница шире экрана: на сколько и какие элементы торчат (корни вылета). */
interface Overflow { by: number; culprits: string[] }
interface Shot {
  row: string; screen: string; width: Width; theme: string; file: string;
  overflow: Overflow | null;
}
const shots: Shot[] = [];

/** Нарушения доступности (axe-core, WCAG 2.1 A/AA) — по экрану и теме, H6. */
interface A11yEntry {
  row: string;
  screen: string;
  theme: string;
  violations: Array<{ id: string; impact: string | null; help: string; nodes: number;
                      targets: string[] }>;
}

/** Для контраста — сами цвета и отношение: «ниже нормы» без пары цветов не починить. */
function contrastSample(node: { target: unknown[]; any: Array<{ data?: unknown }> }): string {
  const d = node.any[0]?.data as
    { fgColor?: string; bgColor?: string; contrastRatio?: number } | undefined;
  const where = node.target.join(" ");
  return d?.fgColor ? `${where}: ${d.fgColor} на ${d.bgColor} = ${d.contrastRatio}:1` : where;
}
const a11y: A11yEntry[] = [];

/**
 * Проверка доступности кадра. Только на настольной ширине: контраст зависит от темы, а
 * разметка (подписи полей, имена кнопок, роли) от ширины почти не зависит — гонять её
 * трижды значило бы втрое удлинить прогон ради тех же находок.
 */
async function audit(page: Page, row: string, screen: string, theme: string) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  a11y.push({
    row, screen, theme,
    violations: result.violations.map((v) => ({
      id: v.id, impact: v.impact ?? null, help: v.help, nodes: v.nodes.length,
      targets: v.nodes.slice(0, 5).map((n) =>
        v.id === "color-contrast" ? contrastSample(n) : n.target.join(" ")),
    })),
  });
}

/**
 * Вылет за край экрана — объективная часть просмотра: глаз пропускает обрезанный на
 * два пикселя край, а геометрия — нет. Считается **любой** элемент правее экрана, а не
 * только прокрутка страницы: карточка с `overflow: hidden` обрезает содержимое молча, и
 * страница при этом не прокручивается (так и нашлась форма входа на телефоне). Виновник
 * — элемент за краем, у которого родитель ещё в экране. Не считаются: содержимое
 * контейнеров со своей прокруткой (таблицы — вылет законный) и фиксированные слои
 * (меню и тосты уезжают за край, пока закрыты).
 */
async function measureOverflow(page: Page): Promise<Overflow | null> {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const by = Math.max(0, document.documentElement.scrollWidth - vw);
    const excused = (el: Element) => {
      for (let a: Element | null = el; a && a !== document.body; a = a.parentElement) {
        const cs = getComputedStyle(a);
        if (cs.position === "fixed") return true;
        if (a !== el && (cs.overflowX === "auto" || cs.overflowX === "scroll")) return true;
        // Внутренность графика обрезается его рамкой по замыслу (прозрачные зоны
        // наведения у краёв); вылезший график поймается по самому <svg>.
        if (a !== el && a.tagName.toLowerCase() === "svg") return true;
      }
      return false;
    };
    const culprits = [...document.querySelectorAll("body *")]
      .filter((el) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0 || r.right <= vw + 1) return false;
        if (getComputedStyle(el).visibility === "hidden") return false;
        const parent = el.parentElement?.getBoundingClientRect();
        return (!parent || parent.right <= vw + 1) && !excused(el);
      })
      .slice(0, 6)
      .map((el) => {
        const cls = [...el.classList].slice(0, 3).join(".");
        return `${el.tagName.toLowerCase()}${cls ? "." + cls : ""} → ${Math.round(el.getBoundingClientRect().right)}px`;
      });
    return by > 1 || culprits.length ? { by, culprits } : null;
  });
}

/**
 * Тема — **до** загрузки страницы, как у человека, переключившего её раньше. Первый
 * прогон менял атрибут поверх открытой страницы, и снимок врал: в тёмном меню стояло
 * «Тема: Светлая» — состояние приложения о смене не знало.
 */
async function presetTheme(page: Page, theme: string) {
  if (page.url() === "about:blank") await page.goto("/login");
  await page.evaluate((t) => localStorage.setItem("fe_theme", t), theme);
}

/** Снять экран во всех вариантах: ширина и тема задаются **до** открытия — вёрстка и
 *  состояние считаются при загрузке, а не только по событиям. */
async function capture(page: Page, row: string, screen: string,
                       open: (page: Page) => Promise<void>,
                       widths: readonly (typeof WIDTHS)[number][] = WIDTHS) {
  for (const [width, w, h] of widths) {
    await page.setViewportSize({ width: w, height: h });
    for (const theme of THEMES) {
      await presetTheme(page, theme);
      await open(page);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      // Мышь — в угол: после щелчка по вкладке она оставалась над графиком, и снимок
      // ловил всплывающую подсказку, которой на экране без наведения нет.
      await page.mouse.move(0, 0);
      await page.waitForTimeout(300);
      const file = `${row}__${screen}__${width}__${theme}.png`;
      const height = await page.evaluate(() => document.documentElement.scrollHeight);
      const overflow = await measureOverflow(page);
      // `animations: "disabled"`: снимок во всю страницу меняет размер окна, и Chromium
      // перезапускает CSS-анимации — меню пользователя попадало в кадр на 30% появления
      // и выглядело лежащим под страницей (проверено пробой: opacity 0,32 после снимка).
      await page.screenshot({ path: `${OUT}/${file}`, fullPage: true, animations: "disabled",
                              clip: { x: 0, y: 0, width: w, height: Math.min(height, MAX_HEIGHT) } });
      shots.push({ row, screen, width, theme, file, overflow });
      if (width === "desktop") await audit(page, row, screen, theme);
    }
  }
}

function writeGallery() {
  const byScreen = new Map<string, Shot[]>();
  for (const s of shots) {
    const key = `${s.row} · ${s.screen}`;
    byScreen.set(key, [...(byScreen.get(key) ?? []), s]);
  }
  const rows = [...byScreen.entries()].map(([key, list]) => `
    <section><h2>${key}</h2><div class="grid">${list.map((s) => `
      <figure><a href="${s.file}"><img src="${s.file}" loading="lazy" alt="${key}, ${s.width}, ${s.theme}"></a>
      <figcaption>${s.width} · ${s.theme}${s.overflow
        ? `<br><b class="warn">шире экрана на ${s.overflow.by}px:</b> ${s.overflow.culprits.join("; ")}`
        : ""}</figcaption></figure>`).join("")}
    </div></section>`).join("");
  writeFileSync(`${OUT}/index.html`, `<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Матрица P13</title>
<style>body{font:14px system-ui;margin:24px;background:#f4f5f7;color:#16181d}
h2{font-size:15px;margin:28px 0 10px}.grid{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start}
figure{margin:0;background:#fff;border:1px solid #d8dbe0;border-radius:8px;padding:6px}
img{display:block;width:220px;height:auto}figcaption{font-size:12px;color:#5b6270;margin-top:4px;max-width:220px}
.warn{color:#b3261e}</style>
</head><body><h1>Матрица скриншотов P13</h1><p>Снимков: ${shots.length}. Снято: ${new Date().toISOString()}.</p>
${rows}</body></html>`);
  writeFileSync(`${OUT}/a11y.json`, JSON.stringify(a11y, null, 2));
  // Переполнение — отдельным файлом: его читают глазами и сверяют между прогонами.
  writeFileSync(`${OUT}/overflow.json`, JSON.stringify(
    shots.filter((s) => s.overflow).map(({ file, overflow }) => ({ file, ...overflow })), null, 2));
}

/** Удержать ответы API, пока снимается кадр загрузки; отпустить — после всей серии. */
async function holdResponses(page: Page, url: RegExp, fn: () => Promise<void>) {
  const held: Route[] = [];
  await page.route(url, (route) => { held.push(route); });
  try {
    await fn();
  } finally {
    await page.unroute(url);
    for (const route of held) await route.continue().catch(() => undefined);
  }
}

/** Ответить ошибкой — как ответил бы упавший или отказавший сервер. */
async function failResponses(page: Page, url: RegExp, status: number, detail: string,
                       fn: () => Promise<void>) {
  await page.route(url, (route) => route.fulfill(
    { status, contentType: "application/json", body: JSON.stringify({ detail }) }));
  try {
    await fn();
  } finally {
    await page.unroute(url);
  }
}

async function register(page: Page, org: string) {
  await page.addInitScript(() => localStorage.setItem("fe_product", "business"));
  await page.goto("/register");
  await page.getByLabel("ФИО").fill("Матрица Скриншотов");
  await page.getByLabel("Email").fill(`screens-${stamp()}@example.test`);
  await page.getByLabel("Пароль").fill("screens-pass-123");
  await page.getByLabel("Название организации").fill(org);
  await page.getByRole("button", { name: /Создать аккаунт/ }).click();
  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();
}

/** Почта на прогон: база живёт между запусками. */
const stamp = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

async function authHeaders(page: Page): Promise<Record<string, string>> {
  const [token, org] = await page.evaluate(
    () => [localStorage.getItem("fe_token"), localStorage.getItem("fe_org")]);
  return { Authorization: `Bearer ${token}`, "X-Organization-Id": org ?? "" };
}

async function projectFromTemplate(api: APIRequestContext, headers: Record<string, string>,
                                   name: string, actuals = false, months?: number,
                                   priceScale = 1): Promise<string> {
  const model = await (await api.get("/api/v1/templates/production", { headers })).json();
  model.header.name = name;
  if (months) model.header.duration_months = months;
  if (priceScale !== 1) {
    // Восьмизначные суммы — проверка печати: колонка по самому длинному числу (H4).
    for (const line of model.operating_plan.sales)
      line.price = line.price.map((p: string) => String(Number(p) * priceScale));
  }
  if (actuals) {
    // Три месяца факта: без них вкладки «План-факт» на результатах нет вовсе.
    model.actualization = { actual_until: 2, actuals: { C1: ["900000", "1100000", "950000"] } };
  }
  const created = await api.post("/api/v1/projects", { headers, data: { name, model } });
  expect(created.ok()).toBeTruthy();
  const { id } = await created.json();
  expect((await api.post(`/api/v1/projects/${id}/calculate`, { headers })).ok()).toBeTruthy();
  return id;
}

test("матрица скриншотов P13", async ({ page, browser }) => {
  mkdirSync(OUT, { recursive: true });
  // Галерея и отчёт о вылетах пишутся и при падении: снятое до него — тоже результат.
  try {
    await page.emulateMedia({ reducedMotion: "reduce" });   // куб — статичным кадром

    // --- Вход и регистрация: до входа, в своём контексте ---
    const guest = await (await browser.newContext()).newPage();
    await guest.emulateMedia({ reducedMotion: "reduce" });
    await guest.addInitScript(() => localStorage.setItem("fe_product", "business"));
    await capture(guest, "auth", "login", async (p) => {
      await p.goto("/login");
      await expect(p.getByRole("button", { name: /Войти/ }).first()).toBeVisible();
    });
    await capture(guest, "auth", "register", async (p) => {
      await p.goto("/register");
      await expect(p.getByLabel("Email")).toBeVisible();
    });
    await guest.context().close();

    // --- Вход и данные ---
    await register(page, "ООО «Матрица»");

    const headers = await authHeaders(page);
    const api = page.request;
    const main = await projectFromTemplate(api, headers, "Завод полимерной упаковки", true);
    const second = await projectFromTemplate(api, headers, "Дочерний склад");
    // Печатная ширина колонки рассчитана «под 12/24 месяца» (P13) — второй горизонт
    // снимается отдельно, иначе эта половина обещания осталась бы непроверенной.
    const long = await projectFromTemplate(api, headers, "Склад на два года", false, 24);
    const wide = await projectFromTemplate(api, headers, "Оптовая база", false, undefined, 1000);
    const holding = await (await api.post("/api/v1/holdings",
                                           { headers, data: { name: "Группа «Матрица»" } })).json();
    for (const [pid, role] of [[main, "parent"], [second, "subsidiary"]]) {
      await api.post(`/api/v1/holdings/${holding.id}/members`,
                     { headers, data: { project_id: pid, role } });
    }

    // --- Сплеш: живёт, пока грузится профиль, — держим ответ, а не рисуем макет ---
    // Запрос отпускается только после всей серии: `unroute` внутри открытия отпускал его
    // сразу, и пятый прогон снял вместо сплеша уже загруженный список проектов.
    const held: Route[] = [];
    await page.route("**/api/v1/auth/me", (route) => { held.push(route); });
    await capture(page, "auth", "splash", async (p) => {
      await p.goto("/projects");
      await expect(p.getByText(/рабочее пространство/)).toBeVisible();
    });
    await page.unroute("**/api/v1/auth/me");
    for (const route of held) await route.continue().catch(() => undefined);   // страницы уже ушли

    // --- Каркас и списки ---
    await capture(page, "shell", "drawer", async (p) => {
      await p.goto("/projects");
      await p.getByTitle("Меню").click();
      await p.waitForTimeout(300);
    }, WIDTHS.filter(([w]) => w === "mobile"));
    // На телефоне меню пользователя живёт в выдвижной панели (снята выше).
    await capture(page, "shell", "menu", async (p) => {
      await p.goto("/projects");
      await p.locator(".shell-userbtn").click();
      await expect(p.getByRole("button", { name: /Выйти/ })).toBeVisible();
    }, WIDTHS.filter(([w]) => w !== "mobile"));
    await capture(page, "projects", "list", async (p) => {
      await p.goto("/projects");
      await expect(p.getByText("Завод полимерной упаковки").first()).toBeVisible();
    });
    await capture(page, "projects", "onboarding", async (p) => {
      await p.goto("/projects/onboarding");
      await expect(p.getByRole("heading", { name: "Что вы планируете" })).toBeVisible();
    });

    // --- Редактор ---
    const editor = async (p: Page, tab: string, label: string) => {
      await p.goto(`/projects/${main}?tab=${tab}`);
      await expect(p.getByRole("button", { name: /Рассчитать/ })).toBeVisible();
      await expect(p.getByText(label).first()).toBeVisible();
    };
    for (const [tab, label] of [["general", "Налоги"], ["sales", "Сбыт"], ["costs", "Издержки"],
                                ["assets", "Инвестиции"]] as const) {
      await capture(page, "editor1", tab, (p) => editor(p, tab, label));
    }
    for (const [tab, label] of [["financing", "Финансирование"], ["currency", "Валюта"],
                                ["actual", "Факт"]] as const) {
      await capture(page, "editor2", tab, (p) => editor(p, tab, label));
    }

    // --- Результаты ---
    const results = async (p: Page, tab: string | null, id = main) => {
      await p.goto(`/projects/${id}/results`);
      await expect(p.getByText(/NPV/).first()).toBeVisible({ timeout: 30_000 });
      if (tab) await p.getByRole("button", { name: tab, exact: true }).first().click();
      await p.waitForTimeout(400);
    };
    for (const [key, tab] of [["summary", null], ["income", "Прибыли и убытки"],
                              ["balance", "Баланс"], ["ratios", "Коэффициенты"],
                              ["charts", "Графики"]] as const) {
      await capture(page, "results", key, (p) => results(p, tab));
    }
    await capture(page, "planfact", "planfact", (p) => results(p, "План-факт"));
    const print = (id: string) => async (p: Page) => {
      await results(p, null, id);
      await p.getByRole("button", { name: /Печать/ }).first().click();
      await expect(p.getByText(/Печатная версия/)).toBeVisible();
    };
    await capture(page, "planfact", "print", print(main));
    await capture(page, "planfact", "print-24", print(long), WIDTHS.filter(([w]) => w === "desktop"));
    // Восьмизначные суммы: колонка — по самому длинному числу, листов больше (H4).
    await capture(page, "planfact", "print-wide", print(wide), WIDTHS.filter(([w]) => w === "desktop"));

    // --- Анализ ---
    // Каждая вкладка ждёт своего содержимого: ревью, снятое по таймеру, попало в кадр
    // крутилкой «Прогоняем ревью…», а шапка — без названия проекта (запрос не успел).
    const analysis = async (p: Page, tab: string) => {
      await p.goto(`/projects/${main}/analysis`);
      await expect(p.locator(".subheader__title")).toHaveText("Завод полимерной упаковки");
      await p.getByRole("button", { name: new RegExp(tab) }).first().click();
    };
    const tabs: Array<[string, string, (p: Page) => Promise<void>]> = [
      ["review", "Ревью плана",
       (p) => expect(p.locator(".rv-count").first()).toBeVisible({ timeout: 60_000 })],
      ["sensitivity", "Чувствительность", (p) => p.waitForTimeout(400)],
      ["sensitivity-result", "Чувствительность", async (p) => {
        await p.getByRole("button", { name: "Рассчитать" }).click();
        await expect(p.getByText("NPV в зависимости от коэффициента")).toBeVisible({ timeout: 60_000 });
      }],
      ["montecarlo", "Монте-Карло", (p) => p.waitForTimeout(400)],
      // Итог Монте-Карло: для съёмки очередь задач работает «сразу» (playwright.config,
      // SCREENS=1) — брокера в e2e нет, а сквозные тесты идут прежним путём.
      ["montecarlo-result", "Монте-Карло", async (p) => {
        await p.getByRole("button", { name: "Запустить" }).click();
        await expect(p.getByText("Распределение NPV", { exact: true })).toBeVisible({ timeout: 90_000 });
      }],
      ["whatif", "What-If", (p) => p.waitForTimeout(400)],
    ];
    for (const [key, tab, ready] of tabs) {
      await capture(page, "analysis", key, async (p) => {
        await analysis(p, tab);
        await ready(p);
      });
    }

    // --- Холдинги и организация ---
    await capture(page, "holdings", "list", async (p) => {
      await p.goto("/holdings");
      await expect(p.getByText("Группа «Матрица»").first()).toBeVisible();
    });
    await capture(page, "holdings", "detail", async (p) => {
      await p.goto(`/holdings/${holding.id}`);
      await expect(p.getByText("Группа «Матрица»").first()).toBeVisible();
      // Имя участника ждём видимым: на телефоне оно сжималось до нуля (P13, G15).
      await expect(p.getByText("Дочерний склад").first()).toBeVisible();
      await p.waitForTimeout(400);
    });
    for (const tab of ["members", "billing"] as const) {
      await capture(page, "org", tab, async (p) => {
        await p.goto(`/organization?tab=${tab}`);
        // Заголовок страницы, а не шапка: в шапке имя организации на планшете скрыто.
        await expect(p.getByRole("heading", { name: "ООО «Матрица»" })).toBeVisible();
        await p.waitForTimeout(600);
      });
    }

    // --- Состояния: загрузка, пусто, ошибка (столбец «Состояния» P13) ---
    // Загрузка — удержанием ответа, ошибка — ответом сервера, пустота — вторым
    // пользователем с новой организацией. Макетов не рисуем: снимается тот экран, который
    // человек увидел бы при медленном или упавшем сервере.
    const LIST = /\/api\/v1\/projects(\?.*)?$/;
    const PROJECT = new RegExp(`/api/v1/projects/${main}$`);
    const CALC = new RegExp(`/api/v1/projects/${main}/calculate`);
    const REVIEW = new RegExp(`/api/v1/projects/${main}/review`);
    const HOLDINGS = /\/api\/v1\/holdings(\?.*)?$/;
    const MEMBERS = /\/api\/v1\/organizations\/[^/]+\/members(\?.*)?$/;
    const down = "Сервис временно недоступен";

    await holdResponses(page, LIST, () => capture(page, "states", "projects-loading", async (p) => {
      await p.goto("/projects");
      await expect(p.getByRole("heading", { name: "Проекты" })).toBeVisible();
    }));
    await failResponses(page, LIST, 500, down, () => capture(page, "states", "projects-error", async (p) => {
      await p.goto("/projects");
      await expect(p.getByText("Не удалось загрузить проекты")).toBeVisible({ timeout: 15_000 });
    }));
    await holdResponses(page, PROJECT, () => capture(page, "states", "editor-loading", async (p) => {
      await p.goto(`/projects/${main}`);
      await p.waitForTimeout(500);
    }));
    await failResponses(page, PROJECT, 500, down, () => capture(page, "states", "editor-error", async (p) => {
      await p.goto(`/projects/${main}`);
      await expect(p.getByText("Не удалось загрузить проект.")).toBeVisible({ timeout: 15_000 });
    }));
    await holdResponses(page, CALC, () => capture(page, "states", "results-loading", async (p) => {
      await p.goto(`/projects/${main}/results`);
      await expect(p.getByText("Идёт расчёт модели…")).toBeVisible();
    }));
    await failResponses(page, CALC, 422,
      "Стартовый баланс не сходится: актив 1 000 000 ≠ пассив 900 000 (разница 100 000).",
      () => capture(page, "states", "results-error", async (p) => {
        await p.goto(`/projects/${main}/results`);
        await expect(p.getByText("Ошибка расчёта")).toBeVisible({ timeout: 15_000 });
      }));
    await holdResponses(page, REVIEW, () => capture(page, "states", "review-loading", async (p) => {
      await p.goto(`/projects/${main}/analysis`);
      await expect(p.getByText("Прогоняем ревью…")).toBeVisible();
    }));
    await failResponses(page, /\/sensitivity$/, 500, down,
      () => capture(page, "states", "sensitivity-error", async (p) => {
        await p.goto(`/projects/${main}/analysis`);
        await p.getByRole("button", { name: /Чувствительность/ }).first().click();
        await p.getByRole("button", { name: "Рассчитать" }).click();
        await expect(p.getByText("Не удалось рассчитать")).toBeVisible({ timeout: 15_000 });
      }));
    await failResponses(page, HOLDINGS, 500, down, () => capture(page, "states", "holdings-error", async (p) => {
      await p.goto("/holdings");
      await expect(p.getByText("Не удалось загрузить холдинги")).toBeVisible({ timeout: 15_000 });
    }));
    await holdResponses(page, MEMBERS, () => capture(page, "states", "members-loading", async (p) => {
      await p.goto("/organization?tab=members");
      await expect(p.getByRole("heading", { name: "ООО «Матрица»" })).toBeVisible();
      await p.waitForTimeout(400);
    }));
    await failResponses(page, MEMBERS, 500, down, () => capture(page, "states", "members-error", async (p) => {
      await p.goto("/organization?tab=members");
      await expect(p.getByRole("heading", { name: "ООО «Матрица»" })).toBeVisible();
      await p.waitForTimeout(2_500);                 // один повтор запроса — и ответ экрана
    }));

    // Пустые экраны — новая организация без проектов и холдингов.
    const fresh = await (await browser.newContext()).newPage();
    await fresh.emulateMedia({ reducedMotion: "reduce" });
    await register(fresh, "ООО «Пустая»");
    await capture(fresh, "states", "projects-empty", async (p) => {
      await p.goto("/projects");
      await expect(p.getByText("Создайте первый проект")).toBeVisible();
    });
    await capture(fresh, "states", "holdings-empty", async (p) => {
      await p.goto("/holdings");
      await expect(p.getByText("Создайте первый холдинг")).toBeVisible();
    });
    const freshHeaders = await authHeaders(fresh);
    const blank = await (await fresh.request.post("/api/v1/projects",
      { headers: freshHeaders,
        data: { name: "Пустая модель", model: { header: { name: "Пустая модель" } } } })).json();
    await capture(fresh, "states", "sales-empty", async (p) => {
      await p.goto(`/projects/${blank.id}?tab=sales`);
      await expect(p.getByText("Пока нет ни одного продукта")).toBeVisible();
    });
    const emptyGroup = await (await fresh.request.post("/api/v1/holdings",
      { headers: freshHeaders, data: { name: "Группа без участников" } })).json();
    await capture(fresh, "states", "holding-empty", async (p) => {
      await p.goto(`/holdings/${emptyGroup.id}`);
      await expect(p.getByText("В холдинге пока нет проектов")).toBeVisible();
    });
    await fresh.context().close();

    // Ошибки входа и регистрации — до входа, в своём контексте.
    const stranger = await (await browser.newContext()).newPage();
    await stranger.emulateMedia({ reducedMotion: "reduce" });
    await stranger.addInitScript(() => localStorage.setItem("fe_product", "business"));
    await capture(stranger, "states", "login-error", async (p) => {
      await p.goto("/login");
      await p.getByLabel("Email").fill("nobody@example.test");
      await p.getByLabel("Пароль").fill("wrong-password-1");
      await p.getByRole("button", { name: /Войти/ }).first().click();
      await expect(p.getByRole("alert")).toBeVisible({ timeout: 15_000 });
    });
    await capture(stranger, "states", "register-error", async (p) => {
      await p.goto("/register");
      await p.getByRole("button", { name: /Создать аккаунт/ }).click();
      await p.waitForTimeout(300);
    });
    await stranger.context().close();

  } finally {
    writeGallery();
  }
});
