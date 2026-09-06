import { describe, expect, it } from "vitest";
import type { StatementOut } from "./api/calc";
import { aggregateStatement, type StatementKind } from "./aggregate";
import fixture from "./fixtures/yearlyAggregate.json";

/**
 * Сверка годовой свёртки на экране со свёрткой в DOCX-документе.
 *
 * Правила записаны дважды: `app/docgen.py` сворачивает отчёты для документа,
 * `aggregate.ts` — для переключателя периодов на экране результатов. Совпадать их ничто
 * не заставляло, а расхождение означало бы, что один и тот же проект показывает разные
 * годовые числа в документе и на экране.
 *
 * Фикстуру генерирует `backend/scripts/dump_aggregate_fixture.py` (вход — реальный расчёт
 * в той же форме, что отдаёт API, включая полную точность Decimal), её свежесть стережёт
 * `test_aggregate_fixture.py`.
 */

const { n, statements } = fixture as unknown as {
  n: number;
  statements: Record<string, {
    kind: StatementKind;
    lines: { code: string; label: string; values: string[] }[];
    yearly: Record<string, string[]>;
  }>;
};

/** Деньги → целые копейки: сравниваем то, что увидит пользователь, а не хвосты Decimal. */
const kop = (v: string): number => Math.round(Number(v) * 100);

describe("Годовая свёртка на экране совпадает с документом", () => {
  it.each(Object.keys(statements))("отчёт «%s»", (key) => {
    const { kind, lines, yearly } = statements[key];
    const stmt = { lines } as StatementOut;
    const got = aggregateStatement(stmt, kind, n, "year");

    expect(got.lines.map((l) => l.code)).toEqual(lines.map((l) => l.code));
    for (const line of got.lines) {
      expect(line.values.map(kop), `строка ${line.code}`)
        .toEqual(yearly[line.code].map(kop));
    }
  });

  it("неполный последний год свёрнут, а не отброшен", () => {
    // 30 месяцев = два полных года и неполный третий: именно на нём легче всего ошибиться.
    expect(n % 12).not.toBe(0);
    const income = statements.income;
    expect(income.yearly[income.lines[0].code]).toHaveLength(Math.ceil(n / 12));
  });

  it("P3 округляется один раз, а не по слагаемым", () => {
    // Тождество P3 = P2 + P1 держится по существу, но округление живёт на границе вывода:
    // P3 = округл(P2_точное + ΣP1_точное). Сумма уже округлённых слагаемых даёт другое
    // число — и именно её печатал бы экран, если считать P3 из свёрнутых рядов.
    // Совпадение P3 с документом проверяет основной тест выше; здесь закрепляется правило.
    const pu = statements.profit_use;
    const got = aggregateStatement({ lines: pu.lines } as StatementOut, pu.kind, n, "year");
    const row = (code: string) => got.lines.find((l) => l.code === code)!.values.map(kop);
    const [p1, p2, p3] = [row("P1"), row("P2"), row("P3")];

    const naive = p1.map((v, i) => v + p2[i]);
    // расхождение возможно, но только на копейку округления — не больше
    p3.forEach((v, i) => expect(Math.abs(v - naive[i])).toBeLessThanOrEqual(1));
    // на этих данных оно действительно возникает: правило нагружено, а не декоративно
    expect(p3).not.toEqual(naive);
  });
});
