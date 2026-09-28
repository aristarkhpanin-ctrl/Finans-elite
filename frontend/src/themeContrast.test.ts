import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Контраст текста — у обоих продуктов, в обеих темах (пакет H, H6).
 *
 * Проверка `axe-core` в матрице скриншотов нашла, что третичный текст (`--subtle`) почти
 * везде ниже нормы WCAG AA — 4,5:1 для обычного текста: 3,5–4,1 в светлой «Элите», 3,0 в
 * тёмной, 3,1–3,5 в тёмном «Аудите». Там же — зелёный текстовый акцент светлой «Элиты»:
 * у токена стояла пометка «(AA)», а против белого он давал 4,42:1. Макет задавал эти
 * цвета, и поправлены они **отступлением от него**, а не молча: у «Аудита» — записью в
 * `auditTheme.test.ts`, у «Элиты» — комментарием у токена со значением макета.
 *
 * Требование живое, а не записанное хексом: поменяется фон или цвет — тест скажет, что
 * пара больше не читается. Пары взяты из того, как токены **используются**: текст — на
 * странице, подложке и карточке; чип — своим цветом на своей заливке. Полупрозрачные
 * заливки тёмной темы накладываются на карточку, как на экране.
 */

const root = fileURLToPath(new URL(".", import.meta.url));
const css = readFileSync(root + "styles.css", "utf8");

/**
 * Объявления одного CSS-блока по селектору: токен → значение. Селектор ищется **с начала
 * строки**: `.pr-paper {` встречается и внутри `.print-mode .print-report .pr-paper {`,
 * где токенов нет, — поиск подстроки находил его первым, и проверка печати молча не
 * проверяла ничего (поймано снятием).
 */
function block(selector: string): Record<string, string> {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const at = css.search(new RegExp(`^${escaped} \\{`, "m"));
  expect(at, `в styles.css нет блока ${selector}`).toBeGreaterThanOrEqual(0);
  const body = css.slice(at + selector.length + 2, css.indexOf("\n}", at))
    .replace(/\/\*[\s\S]*?\*\//g, "");
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

const THEMES: Record<string, Record<string, string>> = {
  "Элит, светлая": block(":root"),
  "Элит, тёмная": { ...block(":root"), ...block('[data-theme="dark"]') },
  "Аудит, светлая": { ...block(":root"), ...block(':root[data-product="audit"]') },
  "Аудит, тёмная": {
    ...block(":root"), ...block('[data-theme="dark"]'), ...block(':root[data-product="audit"]'),
    ...block(':root[data-theme="dark"][data-product="audit"]'),
  },
};

function rgb(hex: string): number[] {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}

/** `rgba(...)` поверх непрозрачного фона; сплошной цвет — как есть. */
function flatten(color: string, bg: number[]): number[] {
  const m = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)/.exec(color);
  if (!m) return rgb(color);
  const a = m[4] === undefined ? 1 : Number(m[4]);
  return [1, 2, 3].map((i) => Math.round(a * Number(m[i]) + (1 - a) * bg[i - 1]));
}

function luminance([r, g, b]: number[]): number {
  const f = (c: number) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrast(a: number[], b: number[]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Норма WCAG 2.1 AA для обычного текста (1.4.3). */
const AA = 4.5;

/** Текстовые токены × фоны, на которых стоит текст. */
const TEXT = ["--text", "--muted", "--subtle", "--accent", "--danger", "--danger-text",
              "--warn-text", "--good", "--info"];
const GROUNDS = ["--page-bg", "--app-bg", "--surface", "--surface-2", "--seg-bg"];
/**
 * Цветные подложки: предупреждение, риск, инфо, успех, выделение. Третичный текст на них
 * не живёт — внутри таких блоков он переназначен на вторичный (`--subtle: var(--muted)`,
 * страж ниже), поэтому здесь проверяются основной и вторичный. Подложка полупрозрачная и
 * лежит то на карточке, то на подложке карточки — проверяются оба случая (пакет I:
 * матрица «Аудита» нашла третичный текст 3,8:1 на тёплой подложке тёмной темы).
 */
const TINTS = ["--warn-bg", "--danger-bg", "--info-bg", "--good-bg", "--primary-soft", "--primary-bg"];
/** Чип, бейдж, выбранная вкладка: свой цвет текста на своей заливке. */
const CHIPS: [string, string][] = [
  ["--accent", "--primary-bg"], ["--accent", "--primary-soft"], ["--good", "--good-bg"],
  ["--warn-text", "--warn-bg"], ["--danger-text", "--danger-bg"], ["--info", "--info-bg"],
  ["--primary-text", "--primary"],
];

function weakPairs(th: Record<string, string>): string[] {
  const card = rgb(th["--surface"]);
  const weak: string[] = [];
  const cardAlt = flatten(th["--surface-2"], card);
  for (const tint of TINTS) {
    for (const [under, base] of [["--surface", card], ["--surface-2", cardAlt]] as const) {
      const ground = flatten(th[tint], base);
      for (const fg of ["--text", "--muted"]) {
        const ratio = contrast(flatten(th[fg], ground), ground);
        if (ratio < AA) weak.push(`${fg} на ${tint} поверх ${under}: ${ratio.toFixed(2)}:1`);
      }
    }
  }
  const pairs = [...TEXT.flatMap((t) => GROUNDS.map((g) => [t, g] as [string, string])), ...CHIPS];
  for (const [fg, bg] of pairs) {
    const ground = flatten(th[bg], card);
    const ratio = contrast(flatten(th[fg], ground), ground);
    if (ratio < AA) weak.push(`${fg} на ${bg}: ${ratio.toFixed(2)}:1`);
  }
  return weak;
}

describe("контраст текста — WCAG AA", () => {
  for (const [name, th] of Object.entries(THEMES)) {
    it(`${name} тема: каждый текстовый токен читается на своём фоне`, () => {
      expect(weakPairs(th), "текст ниже 4,5:1 — не прочитать").toEqual([]);
    });
  }

  it("замер работает: значения макета эту проверку не проходят", () => {
    // Защита от «зелёного» теста при сломанном расчёте: ради этих значений сделаны
    // отступления, и прежние цвета обязаны проваливать ту же проверку.
    expect(weakPairs({ ...THEMES["Элит, светлая"], "--subtle": "#6E8270" }))
      .toContain("--subtle на --page-bg: 3.53:1");
    expect(weakPairs({ ...THEMES["Элит, светлая"], "--accent": "#138A45" }))
      .toContain("--accent на --surface: 4.42:1");
    expect(weakPairs({ ...THEMES["Элит, тёмная"], "--subtle": "#677D64" }).length).toBeGreaterThan(0);
    expect(weakPairs({ ...THEMES["Аудит, тёмная"], "--subtle": "#6A5C86" }).length).toBeGreaterThan(0);
  });

  it("на цветной подложке третичный текст переназначен на вторичный", () => {
    // Иначе третичный текст на тёплой подложке тёмной темы — 3,8:1 (пакет I). Поднять сам
    // третичный нельзя: он сравнялся бы с вторичным, и иерархия исчезла бы. Правило одно:
    // любое правило с цветной подложкой объявляет `--subtle: var(--muted)`.
    const tinted = new RegExp(`background(?:-color)?\\s*:\\s*var\\((${TINTS.join("|")})\\)`);
    const missing: string[] = [];
    for (const m of css.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      const selector = m[1].trim();
      if (selector.startsWith(":root") || selector.startsWith("[data-theme")) continue;
      if (tinted.test(m[2]) && !/--subtle\s*:\s*var\(--muted\)/.test(m[2])) missing.push(selector);
    }
    expect(missing, "цветная подложка без переназначения третичного текста").toEqual([]);
  });

  it("текст не приглушается прозрачностью", () => {
    // Прозрачность поверх цвета роняет контраст мимо токенов: примечание «светофора»
    // диагностики с opacity 0,75 давало 3,4:1 (матрица «Аудита», пакет I), а тест
    // токенов этого не видел. Тон — цветом; исключения названы с причиной.
    const allowed: Record<string, string> = {
      "input::placeholder": "заполнитель — пример, а не содержимое: его бледность отличает «пусто» от «0», а в «Аудите» это разные утверждения",
      ".afield__input::placeholder": "то же, у полей входа",
      ".splash__wordmark span": "логотип (WCAG 1.4.3 не требует контраста у логотипов)",
      ".auth-banner__x": "значок «✕» с именем «Скрыть» — нетекстовый контраст 3:1 проходит",
    };
    const dimmed: string[] = [];
    for (const m of css.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      const selector = m[1].trim();
      const body = m[2];
      if (!/(^|[;\s])opacity\s*:\s*0?\.\d/.test(body)) continue;
      if (!/(^|[;\s])(font|font-size|font-weight|color)\s*:/.test(body)) continue;
      if (selector in allowed || /:disabled|--disabled/.test(selector)) continue;
      dimmed.push(selector);
    }
    expect(dimmed, "текст приглушён прозрачностью — задайте тон цветом").toEqual([]);
    for (const selector of Object.keys(allowed)) {
      expect(css.includes(selector + " {"), `исключение ${selector} устарело — удалите`).toBe(true);
    }
  });

  it("неоновая заливка не служит цветом текста", () => {
    // `--primary` — «только заливки действия» (канон обоих макетов). В светлой теме неон
    // против белого даёт ~1,3:1; так были окрашены десять мест, от «Забыли пароль?» до
    // ссылок в обсуждении.
    // Текстом служит `--accent`: в тёмной теме он совпадает с неоном, в светлой читается.
    const offenders = [...css.matchAll(/([^{}]+)\{[^}]*(?:^|[\s;{])color:\s*var\(--primary\)/gm)]
      .map((m) => m[1].trim().split("\n").pop());
    expect(offenders).toEqual([]);
  });

  it("лист печати читается: чернила на бумаге и на подложках строк", () => {
    // Код строки итога стоит на подложке итога, а не на бумаге: проверка «только бумага»
    // пропустила его (axe в матрице нашёл 4,09:1 на подложке подытога).
    for (const selector of [".pr-paper", ".ap-paper"]) {
      const th = block(selector);
      expect(th["--ink"] && th["--faint"], `${selector}: токены листа не прочитаны`).toBeTruthy();
      const grounds = ["--paper", "--subbg", "--grandbg"]
        .filter((g) => g === "--paper" || th[g])
        .map((g) => [g, rgb(th[g] ?? "#FFFFFF")] as const);
      for (const token of ["--ink", "--sub", "--muted", "--faint", "--accent", "--neg", "--attn"]) {
        if (!th[token]) continue;
        for (const [g, ground] of grounds) {
          const ratio = contrast(rgb(th[token]), ground);
          expect(ratio, `${selector} ${token} на ${g}: ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(AA);
        }
      }
    }
  });
});
