import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Страницы не загружают ресурсов со сторонних серверов (пакет L, L5).
 *
 * Политика обработки персональных данных это утверждает, и утверждение должно быть
 * правдой: шрифт с `api.fontshare.com` грузился со **всех** страниц, включая вход и план
 * по ссылке, — адрес посетителя уходил зарубежному сервису до всякого согласия. Теперь
 * шрифты лежат в сборке, а этот страж не даёт вернуть внешнюю загрузку незаметно.
 * Ссылки, по которым человек переходит сам, загрузкой не считаются.
 */

const root = fileURLToPath(new URL("..", import.meta.url));
const EXTERNAL = /(?:https?:)?\/\/[a-z0-9.-]+\.[a-z]{2,}/i;

function files(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) files(path, out);
    else if (/\.(tsx?|css)$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(path);
  }
  return out;
}

describe("сторонние загрузки", () => {
  it("index.html не тянет ни стилей, ни скриптов, ни шрифтов снаружи", () => {
    const html = readFileSync(join(root, "index.html"), "utf8");
    const loads = [...html.matchAll(/<(?:link|script|img|iframe)[^>]*(?:href|src)="([^"]+)"/g)]
      .map((m) => m[1]).filter((url) => EXTERNAL.test(url));
    expect(loads).toEqual([]);
  });

  it("стили не загружают ничего с чужих адресов", () => {
    const offenders: string[] = [];
    for (const path of files(join(root, "src"))) {
      const text = readFileSync(path, "utf8");
      for (const m of text.matchAll(/(?:url\(\s*['"]?|@import\s+['"])([^'")\s]+)/g)) {
        if (EXTERNAL.test(m[1])) offenders.push(`${path}: ${m[1]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("разметка не вставляет внешних скриптов, кадров и картинок", () => {
    const offenders: string[] = [];
    for (const path of files(join(root, "src"))) {
      const text = readFileSync(path, "utf8");
      for (const m of text.matchAll(/<(?:script|iframe|img|link)\b[^>]*\b(?:src|href)=["{`]+([^"}`]+)/g)) {
        if (EXTERNAL.test(m[1])) offenders.push(`${path}: ${m[1]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("сторож выборки: замер видит внешнюю загрузку там, где она есть", () => {
    expect(EXTERNAL.test("https://api.fontshare.com/v2/css")).toBe(true);
    expect(EXTERNAL.test("//cdn.fontshare.com/wf/x.woff2")).toBe(true);
    expect(EXTERNAL.test("./assets/fonts/satoshi-400.woff2")).toBe(false);
  });
});
