import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Контракт ручных зеркал модели.
 *
 * `api/model.ts` (проект «Финанс-Элит») и `api/audit.ts` (дело «Финанс-Аудит») написаны
 * руками — ими типизированы все вкладки редакторов. `schema.d.ts` генерируется из
 * OpenAPI, и CI следит за его свежестью, но зеркала не сверялись ни с чем. Поэтому
 * переименование или удаление поля в бэкенде до сих пор доходило до пользователя молча:
 * `tsc` проходит (зеркало самосогласовано), редактор пишет старый ключ, сервер его
 * игнорирует, введённое значение пропадает без единой ошибки.
 *
 * Здесь имена полей зеркал сверяются с контрактом. Типы намеренно **не** сверяются:
 * зеркало сужает деньги до `string` (чтобы во float-поле нельзя было положить число) и
 * допускает частично заполненные объекты — точное совпадение типов заставило бы его
 * ослабнуть. Ловятся ровно переименования и пропажи.
 */

const root = fileURLToPath(new URL("../..", import.meta.url));
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
  // «Финанс-Аудит»: во фронте суффикс `Out` опущен там, где ответ один-единственный.
  AuditModel: "AuditSubjectModel",
  AuditDiagnostics: "AuditDiagnosticsOut",
  AuditAnalysis: "AuditAnalysisOut",
  AuditAppliedAdjustment: "AuditAdjustmentOut",
  AuditEarnings: "AuditEarningsOut",
  AuditFlag: "AuditFlagOut",
  AuditFlagRegistry: "AuditFlagsOut",
  AuditInputIssue: "AuditInputIssueOut",
  AuditObligationRow: "AuditObligationRowOut",
  AuditMaturityBucket: "AuditMaturityBucketOut",
  AuditObligations: "AuditObligationsOut",
  AuditConsolidation: "AuditConsolidateResponse",
  AuditElimination: "AuditEliminationIn",
};

/** Схема контракта по имени интерфейса (pydantic делит на -Input/-Output). */
function schemaFor(name: string) {
  const target = ALIASES[name] ?? name;
  for (const candidate of [target, `${target}-Input`, `${target}-Output`]) {
    if (schemas[candidate]) return { key: candidate, schema: schemas[candidate] };
  }
  return null;
}

/** Собственные поля интерфейса из текста (без комментариев и вложенных литералов). */
function ownFields(source: string, name: string): string[] {
  const start = source.indexOf(`export interface ${name} `);
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

/**
 * Поля интерфейса **вместе с унаследованными**: `AuditSubjectOut extends
 * AuditSubjectSummary` — обязательные поля контракта лежат в родителе, и без обхода
 * `extends` тест ругался бы на пропажу того, что на месте.
 */
function fieldsOf(source: string, name: string, seen = new Set<string>()): string[] {
  if (seen.has(name)) return [];
  seen.add(name);
  const decl = new RegExp(`export interface ${name} extends ([\\w,\\s]+)\\{`).exec(source);
  const inherited = decl
    ? decl[1].split(",").flatMap((p) => fieldsOf(source, p.trim(), seen))
    : [];
  return [...inherited, ...ownFields(source, name)];
}

/** Зеркала под проверкой: файл и то, сколько интерфейсов в нём ожидается как минимум. */
const MIRRORS: [string, string, number][] = [
  ["модель проекта (model.ts)", readFileSync(new URL("./model.ts", import.meta.url), "utf8"), 30],
  ["дело аудита (audit.ts)", readFileSync(new URL("./audit.ts", import.meta.url), "utf8"), 25],
];

describe.each(MIRRORS)("Зеркало «%s» совпадает с контрактом бэкенда", (_label, src, least) => {
  const interfaces = [...src.matchAll(/export interface (\w+)/g)].map((m) => m[1]);

  it("интерфейсы найдены и их достаточно много (парсер не сломался)", () => {
    expect(interfaces.length).toBeGreaterThan(least);
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
    const extra = fieldsOf(src, name).filter((f) => !known.has(f));
    expect(extra, `поля есть в зеркале, но нет в схеме ${found.key} — ` +
      "редактор запишет их, а сервер молча проигнорирует").toEqual([]);
  });

  it.each(interfaces)("«%s»: обязательные поля контракта присутствуют", (name) => {
    const found = schemaFor(name);
    if (!found) return;
    const mine = new Set(fieldsOf(src, name));
    const missing = (found.schema.required ?? []).filter((f) => !mine.has(f));
    expect(missing, `обязательные поля схемы ${found.key} отсутствуют в зеркале`)
      .toEqual([]);
  });
});

describe("Разбор зеркала", () => {
  it("парсер полей действительно читает поля, а не пустоту", () => {
    // Защита от «зелёного» теста при сломанном разборе: у известного интерфейса
    // поля обязаны найтись, причём именно те.
    expect(fieldsOf(MIRRORS[0][1], "CustomTax").sort())
      .toEqual(["allocation", "base", "formula", "name", "periodicity", "rate"]);
  });

  it("унаследованные поля попадают в разбор", () => {
    // Без обхода `extends` обязательные поля родителя выглядели бы пропавшими.
    expect(fieldsOf(MIRRORS[1][1], "AuditSubjectOut")).toContain("created_at");
  });
});
