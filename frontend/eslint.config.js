import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

// Плоский конфиг ESLint. Проверка типов — на tsc; здесь ловим ошибки логики
// (правила хуков React, тонкости JS/TS), не дублируя type-check.
export default tseslint.config(
  { ignores: ["dist", "src/api/schema.d.ts"] },
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      globals: { ...globals.browser },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
);
