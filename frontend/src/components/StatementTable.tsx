import { useState } from "react";
import type { StatementOut } from "../api/calc";
import { fmtTable } from "../format";

interface Props {
  statement: StatementOut;
  n: number;
  subtotals: Set<string>;
  /** Итоговые строки (grand): I28 / C29 / B20+B34 / P7. */
  grands?: Set<string>;
}

/**
 * Финансовая таблица (макет «Этап 13»): sticky-колонка «код | Статья»,
 * субтотальные и итоговые строки, скобки для отрицательных, «—» для нуля,
 * ховер строки и колонки (по mouseenter заголовка месяца), легенда.
 */
export function StatementTable({ statement, n, subtotals, grands }: Props) {
  const [hoverCol, setHoverCol] = useState<number | null>(null);
  const months = Array.from({ length: n }, (_, i) => i);

  return (
    <div>
      <div className="fin2-wrap fe-scroll">
        <div className="fin2">
          <div className="fin2-row">
            <div className="fin2-corner">
              <span className="fin2-code">код</span>Статья
            </div>
            {months.map((i) => (
              <div
                key={i}
                className="fin2-month"
                onMouseEnter={() => setHoverCol(i)}
                onMouseLeave={() => setHoverCol(null)}
              >
                М{i + 1}
              </div>
            ))}
          </div>

          {statement.lines.map((l) => {
            const kind = grands?.has(l.code)
              ? " fin2-row--grand"
              : subtotals.has(l.code)
                ? " fin2-row--sub"
                : "";
            return (
              <div key={l.code} className={"fin2-row" + kind}>
                <div className="fin2-label" title={l.label}>
                  <span className="fin2-code">{l.code}</span>
                  <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {l.label}
                  </span>
                </div>
                {months.map((i) => {
                  const f = fmtTable(l.values[i]);
                  return (
                    <div
                      key={i}
                      className={
                        "fin2-cell" +
                        (f.kind === "neg" ? " fin2-cell--neg" : f.kind === "zero" ? " fin2-cell--zero" : "") +
                        (hoverCol === i ? " fin2-cell--colhov" : "")
                      }
                    >
                      {f.text}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      <div className="fin2-legend">
        <span>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: "var(--grand-bg)", border: "1px solid var(--border)" }} />
          итоговая строка
        </span>
        <span>
          <span className="fin2-cell--neg" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>(1 234)</span>
          отрицательное
        </span>
        <span>
          <span className="fin2-cell--zero" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>—</span>
          ноль
        </span>
        <span>⇄ таблица прокручивается по горизонтали</span>
      </div>
    </div>
  );
}

export const SUBTOTALS = {
  income: new Set(["I4", "I7", "I8", "I16", "I19", "I23", "I26", "I28"]),
  cashflow: new Set(["C4", "C7", "C13", "C20", "C27", "C29"]),
  balance: new Set(["B8", "B11", "B20", "B25", "B33", "B34"]),
  profit_use: new Set(["P3", "P7"]),
};

export const GRANDS = {
  income: new Set(["I28"]),
  cashflow: new Set(["C29"]),
  balance: new Set(["B20", "B34"]),
  profit_use: new Set(["P7"]),
};
