import { defineConfig } from "vitest/config";

// Юнит-тесты чистой логики (форматтеры, конвертация процентов, разбор вставки).
// Окружение node — DOM не нужен; компонентные тесты (jsdom) — отдельная задача.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
