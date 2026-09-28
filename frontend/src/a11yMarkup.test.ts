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
 *   кроме контейнеров, внутри которых и так есть поля или кнопки.
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

/** Контейнеры с прокруткой, которым `ScrollRegion` не нужен: фокус и так заходит внутрь. */
const SCROLL_WITH_CONTROLS: Record<string, string> = {
  etabs: "полоса вкладок — сами вкладки кнопки",
  "mgrid-wrap": "помесячная сетка — ячейки поля ввода",
  "mc-tbl": "параметры Монте-Карло — селекты и поля",
  "infl-grid": "инфляция по годам — поля ввода",
};

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

  it("таблица со своей прокруткой доступна с клавиатуры", () => {
    const bare: string[] = [];
    for (const { path, text } of FILES) {
      for (const m of text.matchAll(/<(\w+)\s+className="([^"]*\bfe-scroll\b[^"]*)"/g)) {
        if (m[1] === "ScrollRegion") continue;
        const first = m[2].split(/\s+/)[0];
        if (first in SCROLL_WITH_CONTROLS) continue;
        bare.push(`${path}:${lineOf(text, m.index ?? 0)} (${first})`);
      }
    }
    expect(bare, "контейнер с прокруткой без фокуса — ScrollRegion").toEqual([]);
  });

  it("исключения прокрутки не устарели", () => {
    // Запись, которой больше нет в коде, ничего не разрешает, но выглядит решением.
    const used = new Set(FILES.flatMap(({ text }) =>
      [...text.matchAll(/className="([^"]*\bfe-scroll\b[^"]*)"/g)].map((m) => m[1].split(/\s+/)[0])));
    for (const name of Object.keys(SCROLL_WITH_CONTROLS)) {
      expect(used.has(name), `исключение ${name} не используется — удалите`).toBe(true);
    }
  });
});
