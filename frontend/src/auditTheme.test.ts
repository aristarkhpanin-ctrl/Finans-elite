import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { PRODUCTS } from "./components/product";

/**
 * Тема «Финанс-Аудит» сверяется со стиль-гайдом хендоффа.
 *
 * Палитра записана дважды: канон — объект, который **возвращает** `THEME()` внутри
 * `docs/design/finans-audit/«Финанс Аудит - Стиль-гайд.dc.html»`, реализация — токены
 * `:root[data-product="audit"]` в `styles.css`. Совпадать их ничто не заставляло, а
 * разойтись они могут молча: цвет мимо канона выглядит как обычный цвет, `tsc` и сборка
 * его не видят, и обнаруживается расхождение уже глазами на готовом экране.
 *
 * Сверяется **действующее значение через каскад**, а не наличие строки в блоке аудита:
 * токены, совпадающие с базовой темой (danger, warn), там намеренно не дублируются, и
 * требование «объявлено здесь» заставило бы копировать их без нужды.
 *
 * Ту же роль играет тест у первого продукта: правка макета — сначала в `.dc.html`,
 * потом в `styles.css`, иначе эталон перестаёт быть эталоном.
 */

const root = fileURLToPath(new URL(".", import.meta.url));
const css = readFileSync(root + "styles.css", "utf8");
const guide = readFileSync(
  root + "../../docs/design/finans-audit/Финанс Аудит - Стиль-гайд.dc.html", "utf8");

/** Тело первой функции `THEME()` из макета — там и живут оба объекта тем. */
function themeSource(): string {
  const m = /THEME\s*\([^)]*\)\s*\{/.exec(guide);
  if (!m) throw new Error("в стиль-гайде не найдена THEME() — макет изменил структуру");
  let depth = 0;
  const from = m.index + m[0].length - 1;
  for (let i = from; i < guide.length; i++) {
    if (guide[i] === "{") depth++;
    else if (guide[i] === "}" && --depth === 0) return guide.slice(from, i + 1);
  }
  throw new Error("не закрылась THEME()");
}

/** Объект темы (`dark` / `light`) из исходника макета: ключ → строковое значение. */
function guideTheme(name: "dark" | "light"): Record<string, string> {
  const src = themeSource();
  const at = src.indexOf(`const ${name}={`);
  if (at < 0) throw new Error(`в THEME() нет объекта ${name}`);
  let depth = 0;
  const from = src.indexOf("{", at);
  let to = from;
  for (let i = from; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}" && --depth === 0) { to = i; break; }
  }
  const body = src.slice(from + 1, to);
  const out: Record<string, string> = {};
  // Значения — строки в одинарных кавычках; массивы (heat) разбираются отдельно ниже.
  for (const m of body.matchAll(/(\w+)\s*:\s*'([^']*)'/g)) out[m[1]] = m[2];
  for (const m of body.matchAll(/(\w+)\s*:\s*\[([^\]]*)\]/g)) {
    const items = [...m[2].matchAll(/'([^']*)'/g)].map((x) => x[1]);
    items.forEach((v, i) => { out[`${m[1]}${i + 1}`] = v; });
  }
  return out;
}

/** Объявления одного CSS-блока по селектору: токен → значение. */
function block(selector: string): Record<string, string> {
  const at = css.indexOf(selector + " {");
  expect(at, `в styles.css нет блока ${selector}`).toBeGreaterThanOrEqual(0);
  const body = css.slice(at + selector.length + 2, css.indexOf("\n}", at));
  const out: Record<string, string> = {};
  for (const raw of body.split("\n")) {
    // комментарий в конце строки не должен попасть в значение
    for (const m of raw.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      out[m[1]] = m[2].trim();
    }
  }
  return out;
}

/** Действующее значение токена в теме аудита: блок аудита поверх базового. */
function effective(dark: boolean): Record<string, string> {
  return dark
    ? { ...block(":root"), ...block('[data-theme="dark"]'),
        ...block(':root[data-product="audit"]'),
        ...block(':root[data-theme="dark"][data-product="audit"]') }
    : { ...block(":root"), ...block(':root[data-product="audit"]') };
}

/** `rgba(199,125,255,.15)` и `rgba(199, 125, 255, 0.15)` — одно значение. */
function norm(v: string): string {
  return v.toLowerCase().replace(/\s+/g, " ").replace(/\s*,\s*/g, ",")
    .replace(/(^|[^\d])\.(\d)/g, "$10.$2").trim();
}

/** Ключ канона → токен темы. Дублирование ключей и токенов проверяется отдельно. */
const MAP: Record<string, string> = {
  pageBg: "--page-bg", bg: "--app-bg",
  surface: "--surface", surface2: "--surface-2", surface3: "--surface-3", sk: "--sk",
  border: "--border", borderStrong: "--border-strong", gridLine: "--grid-line",
  text: "--text", muted: "--muted", subtle: "--subtle",
  primary: "--primary", primaryHover: "--primary-hover", primaryText: "--primary-text",
  accent: "--accent", primaryBg: "--primary-bg", primarySoft: "--primary-soft",
  good: "--good", goodBg: "--good-bg", goodBorder: "--good-border",
  danger: "--danger", dangerHover: "--danger-hover",
  dangerBg: "--danger-bg", dangerBorder: "--danger-border",
  warn: "--warn", warnBg: "--warn-bg", warnBorder: "--warn-border",
  info: "--info", infoBg: "--info-bg",
  ring: "--ring", shadow: "--shadow", glow: "--glow",
  barBg: "--bar-bg", segBg: "--seg-bg", segActiveBg: "--seg-active-bg",
  headerBg: "--header-bg",
  heat1: "--heat-1", heat2: "--heat-2", heat3: "--heat-3",
  heat4: "--heat-4", heat5: "--heat-5",
  heatText1: "--heat-text-1", heatText2: "--heat-text-2", heatText3: "--heat-text-3",
  heatText4: "--heat-text-4", heatText5: "--heat-text-5",
};

describe("Тема «Финанс-Аудит» совпадает со стиль-гайдом хендоффа", () => {
  it("разбор макета не сломался: канон прочитан целиком", () => {
    const light = guideTheme("light");
    const dark = guideTheme("dark");
    // Защита от «зелёного» теста при сломанном разборе: если regexp перестанет
    // находить значения, объекты окажутся пустыми и все сверки ниже пройдут впустую.
    for (const key of Object.keys(MAP)) {
      expect(light[key], `в light-теме макета нет ключа ${key}`).toBeTruthy();
      expect(dark[key], `в dark-теме макета нет ключа ${key}`).toBeTruthy();
    }
    expect(light.primary).toBe("#C77DFF");
    expect(light.accent).toBe("#7A2BC4");
  });

  for (const [name, dark] of [["светлая", false], ["тёмная", true]] as const) {
    it(`${name} тема: все токены равны канону`, () => {
      const canon = guideTheme(dark ? "dark" : "light");
      const mine = effective(dark);
      const bad: string[] = [];
      for (const [key, token] of Object.entries(MAP)) {
        if (norm(mine[token] ?? "") !== norm(canon[key])) {
          bad.push(`${token}: ${mine[token] ?? "(нет)"} ≠ ${canon[key]} (${key})`);
        }
      }
      expect(bad, "токены разошлись со стиль-гайдом — правьте styles.css под макет")
        .toEqual([]);
    });
  }

  it("текстовый акцент светлой темы отличается от заливки", () => {
    // Неон #C77DFF против белого даёт ~2.7:1 и как текст нечитаем, поэтому светлая тема
    // держит для текста Deep Violet. Если кто-то «причешет» токены, приравняв accent к
    // primary, ссылки и подписи станут нечитаемыми — а выглядеть будет как упрощение.
    const light = effective(false);
    expect(light["--accent"]).toBe("#7A2BC4");
    expect(light["--accent"]).not.toBe(light["--primary"]);
    // В тёмной теме обе роли исполняет неон — там контраста хватает.
    expect(effective(true)["--accent"]).toBe(effective(true)["--primary"]);
  });

  it("свечение есть только в тёмной теме", () => {
    expect(effective(false)["--glow"]).toBe("none");
    expect(effective(true)["--glow"]).toContain("rgba(199, 125, 255");
    // у первого продукта то же правило — иначе токен «живёт» лишь у одного из двух
    expect(block(":root")["--glow"]).toBe("none");
    expect(block('[data-theme="dark"]')["--glow"]).toContain("rgba(127, 238, 100");
  });

  it("акцент куб-марки взят из хендоффа", () => {
    expect(PRODUCTS.audit.cubeAccent).toEqual(["#C77DFF", "#7B3FE4"]);
    expect(PRODUCTS.business.cubeAccent[0]).toBe("#7FEE64");
  });
});
