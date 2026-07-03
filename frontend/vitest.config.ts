import { defineConfig } from "vitest/config";

// Юнит-тесты чистой логики (форматтеры, конвертация процентов, разбор вставки).
// Окружение node — DOM не нужен; компонентные тесты (jsdom) — отдельная задача.
export default defineConfig({
  test: {
    // Чистая логика — node; компонентные тесты берут jsdom через
    // `// @vitest-environment jsdom` в начале файла.
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
