// Псевдоним для схем, сгенерированных из OpenAPI бэкенда.
// Файл schema.d.ts генерируется командой `npm run gen:api` из backend/openapi.json —
// руками не редактировать. Типы ответов API берём отсюда, чтобы они не расходились
// с бэкендом (переименование/смена типа поля → ошибка сборки, а не «тихий» баг).
import type { components } from "./schema";

export type Schema<K extends keyof components["schemas"]> = components["schemas"][K];
