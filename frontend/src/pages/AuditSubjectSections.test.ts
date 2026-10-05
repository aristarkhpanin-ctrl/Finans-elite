import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Разделы дела: структура по макетам **без потери вкладок**.
 *
 * Это и есть механизм из фазы 0 в действии. Группировка вкладок — самая соблазнительная
 * точка, где «привести интерфейс к макетам» превращается в «выбросить то, чего на
 * макетах нет»: коэффициенты, тренды и диагностику там не рисовали вовсе. Поэтому здесь
 * проверяется не вёрстка, а инвариант — каждая вкладка по-прежнему достижима, и ровно
 * из одного раздела.
 *
 * Разбор идёт по исходнику: отрисовать страницу целиком в jsdom дорого (запросы, react-query,
 * роутер), а инвариант касается описания структуры, а не пикселей.
 */

const source = readFileSync(
  fileURLToPath(new URL("./AuditSubjectPage.tsx", import.meta.url)), "utf8");

/** Вкладки из объединения типа `Tab`. */
function declaredTabs(): string[] {
  const m = /type Tab =([\s\S]*?);/.exec(source);
  expect(m, "в AuditSubjectPage не найден тип Tab — разбор устарел").toBeTruthy();
  return [...m![1].matchAll(/"([a-z]+)"/g)].map((x) => x[1]);
}

/** Разделы: `[код, подпись, вкладки]` из константы SECTIONS. */
function sections(): { key: string; label: string; tabs: string[] }[] {
  const at = source.indexOf("const SECTIONS");
  const body = source.slice(source.indexOf("[", at), source.indexOf("];", at));
  return [...body.matchAll(/\["(\w+)",\s*"([^"]+)",\s*\[([^\]]*)\]\]/g)].map((m) => ({
    key: m[1], label: m[2],
    tabs: [...m[3].matchAll(/"(\w+)"/g)].map((x) => x[1]),
  }));
}

describe("Разделы дела", () => {
  it("разбор не сломался: разделы и вкладки прочитаны", () => {
    expect(declaredTabs().length).toBeGreaterThanOrEqual(8);
    expect(sections().length).toBeGreaterThanOrEqual(4);
  });

  it("ни одна вкладка не потеряна при группировке", () => {
    // Главный инвариант перехода на макеты: интерфейс меняется, функционал — нет.
    const inSections = sections().flatMap((s) => s.tabs);
    expect([...inSections].sort()).toEqual([...declaredTabs()].sort());
  });

  it("вкладка принадлежит ровно одному разделу", () => {
    // Иначе один и тот же экран открывался бы из двух мест с разной подсветкой.
    const inSections = sections().flatMap((s) => s.tabs);
    expect(new Set(inSections).size).toBe(inSections.length);
  });

  it("анализ финсостояния собран в свой раздел", () => {
    // Расширение макетов, принятое в фазе 0: у хендоффа такого раздела нет,
    // но выбрасывать коэффициенты, тренды и Альтмана ради полноты картинки нельзя.
    const health = sections().find((s) => s.key === "health");
    expect(health?.label).toBe("Финансовое состояние");
    expect(health?.tabs).toEqual(["ratios", "trends", "diagnostics"]);
  });

  it("ввод и отчёты — один раздел «Отчётность» (Экран 2)", () => {
    const reporting = sections().find((s) => s.key === "reporting");
    expect(reporting?.tabs).toEqual(["input", "reports"]);
  });

  it("у каждой вкладки есть подпись", () => {
    // Вкладка без подписи отрисовалась бы пустой кнопкой во второй полосе.
    const labels = source.slice(source.indexOf("const TAB_LABEL"),
                                source.indexOf("const SECTIONS"));
    for (const tab of declaredTabs()) {
      expect(labels, `нет подписи для вкладки ${tab}`).toContain(`${tab}:`);
    }
  });
});
