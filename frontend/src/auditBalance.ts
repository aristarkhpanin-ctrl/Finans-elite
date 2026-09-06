import { ASSET_LINES, EQLIAB_LINES } from "./api/audit";

/**
 * Сходимость баланса субъекта (актив = пассив) на стороне клиента.
 *
 * Клиент считает её только ради живой реакции на ввод: пока правки не сохранены, спросить
 * сервер не у кого. Как только модель сохранена, **вердикт даёт сервер** — он считает в
 * `Decimal` и требует ровно нуля, тогда как клиент работает с числами двоичной плавающей
 * точки. Раньше страница всегда считала сама и с допуском в полкопейки: при разрыве
 * 0,003 (такое приходит из импорта XLSX и через API) баннер сообщал «баланс сходится»,
 * а анализ рядом выводил оговорку «баланс не сходится» — об одном и том же.
 *
 * Чтобы клиентская оценка не расходилась с сервером на ровном месте, суммы приводятся к
 * **целым копейкам**: тогда `0.1 + 0.2` не даёт хвоста, и сравнение с нулём точное — то
 * же правило, что у сервера, с точностью до копейки. Доли копейки клиент не различает,
 * и потому его ответ и назван предварительным.
 */

const ASSET_CODES = ASSET_LINES.map(([code]) => code);
const EQLIAB_CODES = EQLIAB_LINES.map(([code]) => code);

/** Значение ячейки → целые копейки (пусто/невалидно → 0). */
function kopecks(v: string | undefined): number {
  const x = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(x) ? Math.round(x * 100) : 0;
}

/** Разрывы «актив − пассив» по периодам, в копейках. */
export function balanceGaps(balance: Record<string, string[]>, n: number): number[] {
  const sum = (codes: string[], t: number) =>
    codes.reduce((acc, c) => acc + kopecks(balance[c]?.[t]), 0);
  return Array.from({ length: Math.max(0, n) },
    (_, t) => sum(ASSET_CODES, t) - sum(EQLIAB_CODES, t));
}

/** Баланс сходится, если разрыв ровно нулевой во всех периодах (как на сервере). */
export function allBalanced(gaps: number[]): boolean {
  return gaps.every((g) => g === 0);
}

/** Ряд разрывов из ответа сервера (строки-Decimal) → копейки. */
export function serverGaps(gaps: string[] | undefined): number[] {
  return (gaps ?? []).map((g) => kopecks(g));
}
