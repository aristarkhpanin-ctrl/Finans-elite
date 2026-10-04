import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Разметка доступности — перечнем по исходникам (пакет H, H6).
 *
 * `axe-core` в матрице скриншотов видит только снятые экраны; модалка, которую матрица не
 * открывала, для него не существует. Эти правила ловят нарушение там, где его пишут:
 *
 * - **подпись связана с полем** — `<label htmlFor>` или подпись, оборачивающая поле.
 *   Без связи поле звалось по заполнителю («0»), а селект был безымянным: так нашёлся
 *   21 селект редактора и поля трёх модалок;
 * - **пустой подписи нет** — поле без видимой подписи получает скрытую (`hideLabel`),
 *   а не `label=""`;
 * - **таблица со своей прокруткой — `ScrollRegion`** (фокус с клавиатуры, роль и имя),
 *   кроме контейнеров, внутри которых и так есть поля или кнопки. Что прокручивается,
 *   решает **CSS**, а не пометка в разметке: в H6 страж смотрел на класс `fe-scroll` и
 *   пропустил таблицы, которые прокручиваются только на телефоне (`axe-core` нашёл их,
 *   когда проверка пошла на всех ширинах, — пакет I).
 */

const root = fileURLToPath(new URL(".", import.meta.url));

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const path = join(dir, e.name);
    if (e.isDirectory()) return sources(path);
    return e.name.endsWith(".tsx") && !e.name.includes(".test.") ? [path] : [];
  });
}

/** Исходник без комментариев: в них `<label>` встречается как слово, а не как тег. */
function code(path: string): string {
  return readFileSync(path, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, (m, pre: string) => pre + " ".repeat(m.length - pre.length));
}

const FILES = sources(root).map((path) => ({ path: path.slice(root.length), text: code(path) }));
const lineOf = (text: string, index: number) => text.slice(0, index).split("\n").length;

/** Открывающие теги `<name …>` с учётом фигурных скобок: `=>` внутри атрибута — не конец тега. */
function openingTags(text: string, name: string): Array<{ start: number; tag: string }> {
  const out: Array<{ start: number; tag: string }> = [];
  for (const m of text.matchAll(new RegExp(`<${name}\\b`, "g"))) {
    const start = m.index ?? 0;
    let depth = 0;
    let quote: string | null = null;
    for (let i = start + m[0].length; i < text.length; i++) {
      const c = text[i];
      if (quote) { if (c === quote) quote = null; }
      else if (depth === 0 && (c === '"' || c === "'" || c === "`")) quote = c;
      else if (c === "{") depth++;
      else if (c === "}") depth--;
      else if (c === ">" && depth === 0) { out.push({ start, tag: text.slice(start, i + 1) }); break; }
    }
  }
  return out;
}

/** Контейнеры с прокруткой, которым `ScrollRegion` не нужен: фокус и так заходит внутрь. */
const SCROLL_WITH_CONTROLS: Record<string, string> = {
  etabs: "полоса вкладок — сами вкладки кнопки",
  "mgrid-wrap": "помесячная сетка — ячейки поля ввода",
  "mc-tbl": "параметры Монте-Карло — селекты и поля",
  "infl-grid": "инфляция по годам — поля ввода",
  "fin-chips": "разделы финансирования — кнопки",
  drawer: "выдвижная панель — диалог со своим фокусом и ссылками",
};

/** Слова класса — и из `className="…"`, и из строк внутри `className={"…" + …}`. */
function classWords(tag: string): string[] {
  const expr = /className=(\{(?:[^{}]|\{[^{}]*\})*\}|"[^"]*")/.exec(tag)?.[1] ?? "";
  return [...expr.matchAll(/"([^"]*)"/g)].flatMap((m) => m[1].split(/\s+/)).filter(Boolean);
}

/**
 * Элементы со щелчком, которым клавиатура не нужна, — с причиной (пакет K, K5). Всё
 * остальное со щелчком обязано быть кнопкой или ссылкой.
 */
const CLICK_WITHOUT_KEYBOARD: Record<string, string> = {
  "menu-overlay": "подложка меню закрывает его по щелчку; с клавиатуры — Esc",
  "drawer-overlay": "подложка выдвижной панели; с клавиатуры — Esc",
  "modal-overlay": "подложка модалки; с клавиатуры — Esc",
  "modal-wrap": "поле вокруг модалки закрывает её по щелчку; с клавиатуры — Esc",
  "bg-gantt__row": "строка Гантта лишь подсвечивает карточку этапа; этапы правятся в карточках",
  "bg-gantt__track": "полоса Гантта — то же выделение; сроки правятся в карточках этапов",
};

/**
 * Классы, которые делают элемент контейнером с прокруткой, — из самих стилей: правило с
 * `overflow: auto|scroll`, класс субъекта селектора (`.a .b` — это `b`). Медиа-запросы
 * тоже: таблица, прокручиваемая только на телефоне, — такая же таблица с прокруткой.
 */
function scrollClasses(): Set<string> {
  const css = readFileSync(root + "styles.css", "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const out = new Set<string>();
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!/overflow(-x|-y)?\s*:\s*(auto|scroll)/.test(m[2])) continue;
    for (const sel of m[1].split(",")) {
      const subject = sel.trim().split(/[\s>+~]+/).pop() ?? "";
      for (const c of subject.matchAll(/\.([\w-]+)/g)) out.add(c[1]);
    }
  }
  return out;
}
const SCROLLING = scrollClasses();

describe("разметка доступности", () => {
  it("разбор исходников не пуст", () => {
    // Иначе все проверки ниже прошли бы впустую.
    expect(FILES.length).toBeGreaterThan(50);
    expect(FILES.some((f) => /<label\b/.test(f.text))).toBe(true);
  });

  it("каждая подпись связана с полем", () => {
    const loose: string[] = [];
    for (const { path, text } of FILES) {
      for (const m of text.matchAll(/<label\b([^>]*)>([\s\S]*?)<\/label>/g)) {
        if (/\bhtmlFor=/.test(m[1])) continue;
        // Подпись-обёртка: поле внутри неё (в том числе поле-компонент вроде PctInput).
        if (/<(input|select|textarea)\b|<\w*Input\b/.test(m[2])) continue;
        loose.push(`${path}:${lineOf(text, m.index ?? 0)}`);
      }
    }
    expect(loose, "подпись ни с чем не связана — полю нужен htmlFor/id").toEqual([]);
  });

  it("пустых подписей нет — скрытая подпись вместо пустой", () => {
    const empty = FILES.flatMap(({ path, text }) =>
      [...text.matchAll(/\blabel=""/g)].map((m) => `${path}:${lineOf(text, m.index ?? 0)}`));
    expect(empty, "label=\"\" — поле без имени; нужна подпись с hideLabel").toEqual([]);
  });

  it("классы прокрутки из стилей прочитаны", () => {
    // Сторож разбора: без него «ни один класс не прокручивается» выглядело бы зелёным.
    for (const known of ["fin2-wrap", "contrib-wrap", "sens-table", "org-tbl", "etabs"]) {
      expect(SCROLLING.has(known), `класс ${known} не найден среди прокручиваемых`).toBe(true);
    }
  });

  it("таблица со своей прокруткой доступна с клавиатуры", () => {
    const bare: string[] = [];
    for (const { path, text } of FILES) {
      for (const m of text.matchAll(/<([A-Za-z]\w*)\b[^<>]*?className="([^"]*)"/g)) {
        if (m[1] === "ScrollRegion") continue;
        const scroll = m[2].split(/\s+/).find((c) => SCROLLING.has(c));
        if (!scroll || scroll in SCROLL_WITH_CONTROLS) continue;
        // Заглушка загрузки (скелетон) — не таблица: её помечает aria-busy.
        const start = m.index ?? 0;
        const tag = text.slice(start, text.indexOf(">", start + m[0].length) + 1);
        if (/aria-busy/.test(tag)) continue;
        bare.push(`${path}:${lineOf(text, start)} (${scroll})`);
      }
    }
    expect(bare, "контейнер с прокруткой без фокуса — ScrollRegion").toEqual([]);
  });

  it("выбранный вариант назван не только цветом", () => {
    // Вкладки редактора, результатов, анализа, сегменты и фильтры подсвечивали выбранное
    // только классом — диктор не слышал, какая вкладка открыта (пакет I). Кнопка, у
    // которой подсветка зависит от условия, обязана сказать состояние словами ARIA.
    const mute: string[] = [];
    for (const { path, text } of FILES) {
      for (const { start, tag } of openingTags(text, "button")) {
        const toggles = /--(active|on)"\s*:\s*""|\?\s*"on"\s*:\s*""/.test(tag);
        if (toggles && !/aria-(pressed|selected|checked|current)/.test(tag)) {
          mute.push(`${path}:${lineOf(text, start)}`);
        }
      }
    }
    expect(mute, "подсветка без состояния — нужен aria-pressed или aria-selected").toEqual([]);
  });

  it("разбор тегов видит кнопки-переключатели", () => {
    // Сторож разбора: иначе «нарушений нет» значило бы «кнопок не нашли».
    const toggles = FILES.flatMap(({ text }) => openingTags(text, "button"))
      .filter(({ tag }) => /--active"\s*:\s*""/.test(tag));
    expect(toggles.length).toBeGreaterThan(10);
  });

  it("кнопка-значок названа словами", () => {
    // «✕» у кнопок удаления в Монте-Карло и What-If диктор читал как «знак умножения»:
    // `title` при текстовом содержимом — описание, а не имя (пакет I). Кнопка, в тексте
    // которой нет ни одной буквы, обязана назвать себя через aria-label.
    const glyphOnly: string[] = [];
    for (const { path, text } of FILES) {
      for (const { start, tag } of openingTags(text, "button")) {
        const end = text.indexOf("</button>", start + tag.length);
        if (end < 0) continue;
        const raw = text.slice(start + tag.length, end).replace(/<[^>]*>/g, "");
        // Текст, приходящий выражением `{…}`, по исходнику не узнать — такие кнопки не судим.
        if (raw.includes("{")) continue;
        const inner = raw.replace(/&nbsp;/g, "").trim();
        if (inner && !/\p{L}|\d/u.test(inner) && !/aria-label/.test(tag)) {
          glyphOnly.push(`${path}:${lineOf(text, start)} «${inner}»`);
        }
      }
    }
    expect(glyphOnly, "кнопка без слов — нужен aria-label").toEqual([]);
  });

  it("прокрутка — классом из стилей, а не встроенным стилем", () => {
    // Девятнадцать таблиц «Аудита» прокручивались через style={{ overflowX: "auto" }},
    // и страж прокрутки их не видел: он читает CSS (пакет I, матрица «Аудита»).
    const inline = FILES.flatMap(({ path, text }) =>
      [...text.matchAll(/overflow(X|Y)?:\s*"(auto|scroll)"/g)]
        .map((m) => `${path}:${lineOf(text, m.index ?? 0)}`));
    expect(inline, "встроенная прокрутка — нужен класс (x-scroll) и ScrollRegion").toEqual([]);
  });

  it("у каждого поля есть имя", () => {
    // Селекты периода, поправки и норматива «Аудита» были безымянными, а ячейки сеток
    // звались «0» — по заполнителю (матрица «Аудита», пакет I). Имя даёт aria-label,
    // подпись (id + htmlFor или обёртка <label>) или title. Заполнитель со словами —
    // слабое, но имя (его принимает и axe-core); заполнитель без букв именем не считается.
    const unnamed: string[] = [];
    for (const { path, text } of FILES) {
      const labels = [...text.matchAll(/<label\b[\s\S]*?<\/label>/g)]
        .map((m) => [m.index ?? 0, (m.index ?? 0) + m[0].length]);
      for (const name of ["input", "select", "textarea"]) {
        for (const { start, tag } of openingTags(text, name)) {
          if (/type="(hidden|file|submit)"/.test(tag)) continue;
          if (/aria-label|aria-labelledby|\bid=|\btitle=|\{\.\.\./.test(tag)) continue;
          const ph = /placeholder=(?:"([^"]*)"|\{`([^`]*)`\})/.exec(tag);
          if (ph && /\p{L}/u.test(ph[1] ?? ph[2] ?? "")) continue;
          if (labels.some(([a, z]) => start > a && start < z)) continue;
          unnamed.push(`${path}:${lineOf(text, start)} <${name}>`);
        }
      }
    }
    expect(unnamed, "поле без имени — нужен aria-label или подпись").toEqual([]);
  });

  it("карточка ошибки — только общая ErrorState", () => {
    // Копии разметки жили на шести страницах, и ни в одной не было role="alert":
    // диктор о сбое не узнавал (пакет I). Седьмая копия повторила бы то же.
    const copies = FILES.filter(({ path }) => !path.endsWith("components/ui.tsx"))
      .flatMap(({ path, text }) => [...text.matchAll(/className="error-state"/g)]
        .map((m) => `${path}:${lineOf(text, m.index ?? 0)}`));
    expect(copies, "разметка ошибки мимо ErrorState").toEqual([]);
  });

  it("исключения прокрутки не устарели", () => {
    // Запись, которой больше нет в коде или в стилях, ничего не разрешает, но выглядит решением.
    const used = new Set(FILES.flatMap(({ text }) =>
      [...text.matchAll(/className="([^"]*)"/g)].flatMap((m) => m[1].split(/\s+/))));
    for (const name of Object.keys(SCROLL_WITH_CONTROLS)) {
      expect(used.has(name), `исключение ${name} не используется — удалите`).toBe(true);
      expect(SCROLLING.has(name), `${name} больше не прокручивается — удалите исключение`).toBe(true);
    }
  });

  it("рисунок либо назван, либо скрыт от диктора", () => {
    // SVG без роли и имени диктор читал россыпью подписей осей — «8,4м 12м 0 М1…» (пакет K,
    // K5). Значок рядом со словом — скрыт; график — изображение с подписью у контейнера
    // (`chartA11y`), а сам рисунок тоже скрыт.
    const bare: string[] = [];
    for (const { path, text } of FILES) {
      for (const { start, tag } of openingTags(text, "svg")) {
        const hidden = /aria-hidden="true"/.test(tag) || /\{\.\.\.props\}/.test(tag);
        const named = /role="img"/.test(tag) && /aria-label/.test(tag);
        if (!hidden && !named) bare.push(`${path}:${lineOf(text, start)}`);
      }
    }
    expect(bare, "SVG без имени и не скрытый").toEqual([]);
  });

  it("щелчок — у кнопок и ссылок", () => {
    // Раскрытие слагаемых в отчётах и переключатели легенды чувствительности были `div` и
    // `span` со щелчком: с клавиатуры и для диктора их не существовало (пакет K, K5).
    const stray: string[] = [];
    for (const { path, text } of FILES) {
      for (const name of ["div", "span", "li", "td", "tr", "p", "section"]) {
        for (const { start, tag } of openingTags(text, name)) {
          if (!/\sonClick=/.test(tag)) continue;
          const cls = classWords(tag);
          if (cls.some((c) => c in CLICK_WITHOUT_KEYBOARD) || /role="dialog"/.test(tag)) continue;
          stray.push(`${path}:${lineOf(text, start)} <${name}>`);
        }
      }
    }
    expect(stray, "щелчок на элементе, до которого не дойти с клавиатуры").toEqual([]);
  });

  it("исключения щелчка не устарели", () => {
    const used = new Set(FILES.flatMap(({ text }) =>
      ["div", "span"].flatMap((name) => openingTags(text, name).flatMap(({ tag }) => classWords(tag)))));
    for (const name of Object.keys(CLICK_WITHOUT_KEYBOARD)) {
      expect(used.has(name), `исключение щелчка ${name} не используется — удалите`).toBe(true);
    }
  });
});
