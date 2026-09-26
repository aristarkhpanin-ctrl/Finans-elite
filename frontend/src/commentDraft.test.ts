// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearAllDrafts, clearDraft, draftKey, readDraft, writeDraft,
         DRAFT_NOTE } from "./commentDraft";

/**
 * Черновик реплики (F9).
 *
 * Проверяется не «строка положилась в хранилище», а обещания: черновик принадлежит
 * **ветке** (обсуждение о цене не подставляет текст из обсуждения сроков), пустой текст
 * **стирает** запись, выход из системы уносит все черновики, а запрещённое хранилище
 * **не роняет** панель — в приватном окне доступ к `localStorage` бросает исключение.
 */

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

it("черновик принадлежит ветке, а не сущности целиком", () => {
  // «Обсуждение проекта» без места — чат, из которого не понять, о чём шла речь; у
  // черновика та же беда, если ключ не различает места.
  const price = draftKey("project", "p1", "line:income:I1");
  const dates = draftKey("project", "p1", "tab:calendar");
  writeDraft(price, "почему выручка падает в марте?");

  expect(readDraft(price)).toBe("почему выручка падает в марте?");
  expect(readDraft(dates)).toBe("");
});

it("черновики разных сущностей не смешиваются", () => {
  writeDraft(draftKey("project", "p1"), "о проекте");
  writeDraft(draftKey("case", "p1"), "о деле");

  expect(readDraft(draftKey("project", "p1"))).toBe("о проекте");
  expect(readDraft(draftKey("case", "p1"))).toBe("о деле");
});

it("пустой текст стирает черновик, а не пишет пустую строку", () => {
  // Иначе «черновик остался» показывалось бы тому, кто всё стёр сам.
  const key = draftKey("project", "p1");
  writeDraft(key, "набрал");
  writeDraft(key, "   ");

  expect(readDraft(key)).toBe("");
  expect(localStorage.getItem(key)).toBeNull();
});

it("отправленная реплика черновиком больше не является", () => {
  const key = draftKey("project", "p1");
  writeDraft(key, "вопрос");
  clearDraft(key);
  expect(readDraft(key)).toBe("");
});

it("выход из системы уносит все черновики", () => {
  // Несказанные слова принадлежат тому, кто их набрал: следующему человеку за этим же
  // браузером их видеть незачем.
  writeDraft(draftKey("project", "p1"), "первый");
  writeDraft(draftKey("case", "c1", "tab:valuation"), "второй");
  localStorage.setItem("fe.token", "чужое-не-трогаем");

  clearAllDrafts();

  expect(readDraft(draftKey("project", "p1"))).toBe("");
  expect(readDraft(draftKey("case", "c1", "tab:valuation"))).toBe("");
  expect(localStorage.getItem("fe.token")).toBe("чужое-не-трогаем");
});

it("стирание не пропускает половину записей", () => {
  // Удаление по ходу обхода сдвигает индексы, и половина черновиков осталась бы — та,
  // которую труднее всего заметить.
  for (let i = 0; i < 10; i += 1) writeDraft(draftKey("project", `p${i}`), `текст ${i}`);
  clearAllDrafts();

  for (let i = 0; i < 10; i += 1) expect(readDraft(draftKey("project", `p${i}`))).toBe("");
});

describe("запрещённое хранилище", () => {
  /** Приватное окно: доступ к `localStorage` **бросает**, а не возвращает null. */
  function forbid() {
    const angry = () => { throw new DOMException("доступ запрещён", "SecurityError"); };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(angry);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(angry);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(angry);
  }

  it("чтение не роняет панель", () => {
    forbid();
    expect(readDraft(draftKey("project", "p1"))).toBe("");
  });

  it("запись не роняет панель", () => {
    forbid();
    expect(() => writeDraft(draftKey("project", "p1"), "текст")).not.toThrow();
  });

  it("выход не роняет приложение", () => {
    forbid();
    expect(() => clearAllDrafts()).not.toThrow();
  });
});

it("обещание сказано буквально: черновик локальный", () => {
  // Пообещать, что он найдётся на другом устройстве, нельзя — а молча не найтись хуже,
  // чем честно сказать заранее.
  expect(DRAFT_NOTE).toContain("в этом браузере");
  expect(DRAFT_NOTE).toContain("после выхода");
});
