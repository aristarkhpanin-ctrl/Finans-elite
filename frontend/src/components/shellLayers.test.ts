import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Порядок слоёв оболочки — тот самый класс ошибок, который не ловит ни один тест в jsdom:
 * там нет ни раскладки, ни отрисовки, и `fireEvent.click` попадает в элемент, даже если
 * поверх него лежит перехватчик. Поэтому инвариант проверяется прямо по `styles.css`.
 *
 * История: шапка стояла на `z-index: 30`, а оверлей, закрывающий меню по клику вне его, —
 * на 40. Шапка создаёт контекст наложения, поэтому `z-index: 50` у меню считался внутри
 * неё, а не от корня: меню было **видно**, но все клики забирал оверлей. Со стороны это
 * выглядело как «переключатель продукта не работает» — и второй продукт был недостижим.
 */

// Комментарии вырезаются: в блоке шапки объяснение упоминает «z-index: 50», и разбор
// без очистки читал число из текста, а не из объявления — тест проходил бы и на сломанном.
const css = readFileSync(fileURLToPath(new URL("../styles.css", import.meta.url)), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "");

/**
 * Действующий z-index селектора: у некоторых классов в `styles.css` есть переопределяющий
 * блок ниже по файлу (например, у `.save-bar`), поэтому берётся **последнее** правило —
 * то, что и побеждает в каскаде.
 */
function zIndex(selector: string): number {
  let found: number | null = null;
  let seen = false;
  for (let at = css.indexOf(selector + " {"); at >= 0;
       at = css.indexOf(selector + " {", at + 1)) {
    seen = true;
    const m = css.slice(at, css.indexOf("}", at)).match(/z-index:\s*(-?\d+)/);
    if (m) found = Number(m[1]);
  }
  expect(seen, `селектор ${selector} не найден в styles.css`).toBe(true);
  expect(found, `у ${selector} не задан z-index`).not.toBeNull();
  return found!;
}

describe("Слои оболочки", () => {
  it("шапка выше оверлея меню — иначе меню видно, но не нажимается", () => {
    expect(zIndex(".shell-header")).toBeGreaterThan(zIndex(".menu-overlay"));
  });

  it("оверлей выше содержимого страницы — клик вне меню его закрывает", () => {
    // Панель сохранения — самый «высокий» элемент контента; оверлей должен накрывать и её.
    expect(zIndex(".menu-overlay")).toBeGreaterThan(zIndex(".save-bar"));
  });

  it("мобильный drawer и его подложка выше шапки — иначе шапка торчит поверх", () => {
    const header = zIndex(".shell-header");
    expect(zIndex(".drawer-overlay")).toBeGreaterThan(header);
    expect(zIndex(".drawer")).toBeGreaterThan(zIndex(".drawer-overlay"));
  });

  it("модальные окна и уведомления выше всей оболочки", () => {
    const drawer = zIndex(".drawer");
    expect(zIndex(".modal-overlay")).toBeGreaterThan(drawer);
    expect(zIndex(".toast-layer")).toBeGreaterThan(zIndex(".modal-overlay"));
  });
});

/**
 * Правила рейла, которые не проверить в jsdom: там нет ни раскладки, ни медиазапросов,
 * поэтому узкое состояние существует только в CSS. Проверяется решение, а не оформление.
 */
describe("Узкий рейл", () => {
  /**
   * Тело правила `selector` внутри медиазапроса `at`. Такой медиазапрос в файле не
   * один, поэтому перебираются все его блоки и берётся тот, где правило есть: поиск
   * «от первого вхождения» находил базовое правило выше по файлу и молча проверял
   * не то, что нужно.
   */
  function ruleIn(at: string, selector: string): string {
    for (let i = css.indexOf(at); i >= 0; i = css.indexOf(at, i + 1)) {
      let depth = 0;
      const open = css.indexOf("{", i);
      let close = open;
      for (let j = open; j < css.length; j++) {
        if (css[j] === "{") depth++;
        else if (css[j] === "}" && --depth === 0) { close = j; break; }
      }
      const body = css.slice(open + 1, close);
      const at2 = body.indexOf(selector + " {");
      if (at2 >= 0) return body.slice(at2, body.indexOf("}", at2));
    }
    throw new Error(`внутри ${at} нет правила ${selector}`);
  }

  it("заголовок раздела скрыт визуально, но остаётся в доступности", () => {
    // «ОРГАНИЗАЦИЯ» в 76px не помещалась и вылезала в контент. Убрать её напрашивалось
    // через display:none — но тогда пропала бы и группировка разделов для скринридера,
    // а группировка это смысл, а не оформление.
    const rule = ruleIn("@media (max-width: 1023px)", ".rail__title");
    expect(rule, "display:none выкинул бы заголовок и из доступности")
      .not.toContain("display: none");
    expect(rule, "без обрезки заголовок вылезет за границу рейла").toContain("clip-path");
  });

  it("на телефоне рейла нет вовсе — навигация возвращается в drawer", () => {
    expect(ruleIn("@media (max-width: 640px)", ".rail")).toContain("display: none");
  });
});
