// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Ошибки интерфейса (G7): уходят только там, где трекер включён; без строки запроса;
 * не больше нескольких за загрузку, повтор той же — нет; отправка никогда не бросает.
 */

const post = vi.fn();
const getCapabilities = vi.fn();
vi.mock("./api/client", () => ({ api: { post: (...a: unknown[]) => post(...a) } }));
vi.mock("./api/auth", () => ({ getCapabilities: () => getCapabilities() }));

import { MAX_REPORTS_PER_LOAD, reportClientError,
         resetErrorReportingForTests } from "./errorReport";

beforeEach(() => {
  vi.clearAllMocks();
  resetErrorReportingForTests();
  post.mockResolvedValue({});
  getCapabilities.mockResolvedValue({ mail: false, error_tracking: true });
  window.history.pushState({}, "", "/projects/p1?token=secret#tab");
});
afterEach(() => window.history.pushState({}, "", "/"));

describe("отчёт об ошибке интерфейса", () => {
  it("уходит без строки запроса — в ней ходят токены ссылок", async () => {
    await reportClientError(new TypeError("x is undefined"));
    expect(post).toHaveBeenCalledTimes(1);
    const body = post.mock.calls[0][1];
    expect(body.path).toBe("/projects/p1");
    expect(body.message).toBe("TypeError: x is undefined");
    expect(JSON.stringify(body)).not.toContain("secret");
  });

  it("где трекер выключен, не уходит вовсе", async () => {
    getCapabilities.mockResolvedValue({ mail: false, error_tracking: false });
    await reportClientError(new Error("x"));
    expect(post).not.toHaveBeenCalled();
  });

  it("повтор той же ошибки не уходит, и предел на загрузку держится", async () => {
    await reportClientError(new Error("одна и та же"));
    await reportClientError(new Error("одна и та же"));
    expect(post).toHaveBeenCalledTimes(1);
    for (let i = 0; i < MAX_REPORTS_PER_LOAD + 3; i += 1) {
      await reportClientError(new Error(`разная ${i}`));
    }
    expect(post).toHaveBeenCalledTimes(MAX_REPORTS_PER_LOAD);
  });

  it("возможности спрашиваются один раз за загрузку", async () => {
    await reportClientError(new Error("a"));
    await reportClientError(new Error("b"));
    expect(getCapabilities).toHaveBeenCalledTimes(1);
  });

  it("отказ сервера не рождает новую ошибку", async () => {
    post.mockRejectedValue(new Error("сеть"));
    await expect(reportClientError(new Error("x"))).resolves.toBeUndefined();
    getCapabilities.mockRejectedValue(new Error("сеть"));
    resetErrorReportingForTests();
    await expect(reportClientError("строкой")).resolves.toBeUndefined();
  });
});
