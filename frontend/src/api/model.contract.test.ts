import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Контракт ручного зеркала модели.
 *
 * `api/model.ts` написан руками — им типизированы все вкладки редактора. `schema.d.ts`
 * генерируется из OpenAPI, и CI следит за его свежестью, но зеркало не сверялось ни с чем.
 * Поэтому переименование или удаление поля в бэкенде до сих пор доходило до пользователя
 * молча: `tsc` проходит (зеркало самосогласовано), редактор пишет старый ключ, сервер его
 * игнорирует, введённое значение пропадает без единой ошибки.
 *
 * Здесь имена полей зеркала сверяются с контрактом. Типы намеренно **не** сверяются:
 * зеркало сужает деньги до `string` (чтобы во float-поле нельзя было положить число) и
 * допускает частично заполненные объекты — точное совпадение типов заставило бы его
 * ослабнуть. Ловятся ровно переименования и пропажи.
 */

const root = fileURLToPath(new URL("../..", import.meta.url));
const modelTs = readFileSync(new URL("./model.ts", import.meta.url), "utf8");
const spec = JSON.parse(readFileSync(root + "../backend/openapi.json", "utf8"));
const schemas: Record<string, { properties?: Record<string, unknown>; required?: string[] }> =
  spec.components.schemas;

/**
 * Интерфейсы, названные во фронтенде иначе, чем в контракте. Список явный: молчаливый
 * пропуск незнакомого имени означал бы, что зеркало можно расширять мимо проверки.
 */
const ALIASES: Record<string, string> = {
  CustomTax: "Tax",             // в бэкенде просто Tax, во фронте уточнено «настраиваемый»
  ProjectDetail: "ProjectOut",  // ответ GET /projects/{id}
};

/** Схема контракта по имени интерфейса (pydantic делит на -Input/-Output). */
function schemaFor(name: string) {
  const target = ALIASES[name] ?? name;
  for (const candidate of [target, `${target}-Input`, `${target}-Output`]) {
    if (schemas[candidate]) return { key: candidate, schema: schemas[candidate] };
  }
  return null;
}

/** Поля интерфейса из текста `model.ts` (без комментариев и вложенных литералов). */
function fieldsOf(source: string, name: string): string[] {
  const start = source.indexOf(`export interface ${name} {`);
  if (start < 0) return [];
  let depth = 0;
  let i = source.indexOf("{", start);
  const open = i;
  for (; i < source.length; i++) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}" && --depth === 0) break;
  }
  const body = source.slice(open + 1, i);
  const out: string[] = [];
  let nest = 0;
  for (const raw of body.split("\n")) {
    const line = raw.replace(/\/\/.*$/, "").trim();
    if (!line) continue;
    // поля вложенных литералов к этому интерфейсу не относятся
    if (nest === 0) {
      const m = /^(\w+)\??\s*:/.exec(line);
      if (m) out.push(m[1]);
    }
    nest += (line.match(/\{/g) ?? []).length - (line.match(/\}/g) ?? []).length;
  }
  return out;
}

const interfaces = [...modelTs.matchAll(/export interface (\w+)/g)].map((m) => m[1]);

describe("Зеркало модели совпадает с контрактом бэкенда", () => {
  it("интерфейсы найдены и их достаточно много (парсер не сломался)", () => {
    expect(interfaces.length).toBeGreaterThan(30);
  });

  it("у каждого интерфейса есть схема в контракте", () => {
    const orphans = interfaces.filter((n) => !schemaFor(n));
    expect(orphans, "нет схемы в openapi.json — переименовано или удалено в бэкенде")
      .toEqual([]);
  });

  it.each(interfaces)("«%s»: полей мимо контракта нет", (name) => {
    const found = schemaFor(name);
    if (!found) return;                       // покрыто отдельным тестом выше
    const known = new Set(Object.keys(found.schema.properties ?? {}));
    const extra = fieldsOf(modelTs, name).filter((f) => !known.has(f));
    expect(extra, `поля есть в зеркале, но нет в схеме ${found.key} — ` +
      "редактор запишет их, а сервер молча проигнорирует").toEqual([]);
  });

  it.each(interfaces)("«%s»: обязательные поля контракта присутствуют", (name) => {
    const found = schemaFor(name);
    if (!found) return;
    const mine = new Set(fieldsOf(modelTs, name));
    const missing = (found.schema.required ?? []).filter((f) => !mine.has(f));
    expect(missing, `обязательные поля схемы ${found.key} отсутствуют в зеркале`)
      .toEqual([]);
  });

  it("парсер полей действительно читает поля, а не пустоту", () => {
    // Защита от «зелёного» теста при сломанном разборе: у известного интерфейса
    // поля обязаны найтись, причём именно те.
    expect(fieldsOf(modelTs, "CustomTax").sort())
      .toEqual(["allocation", "base", "formula", "name", "periodicity", "rate"]);
  });
});
