import type { StatementOut } from "../api/calc";
import { money } from "../format";

interface Props {
  statement: StatementOut;
  n: number;
  subtotals: Set<string>;
}

/** Плотная финансовая таблица: строки = статьи, столбцы = месяцы. */
export function StatementTable({ statement, n, subtotals }: Props) {
  const months = Array.from({ length: n }, (_, i) => i + 1);
  return (
    <div className="fin-table-wrap">
      <table className="fin-table">
        <thead>
          <tr>
            <th className="label-col">Статья</th>
            {months.map((m) => (
              <th key={m} className="num">М{m}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {statement.lines.map((l) => (
            <tr key={l.code} className={subtotals.has(l.code) ? "subtotal" : ""}>
              <td className="label-col" title={l.label}>
                <span className="code">{l.code}</span>
                {l.label}
              </td>
              {months.map((_, i) => (
                <td key={i} className="num">
                  {money(l.values[i])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const SUBTOTALS = {
  income: new Set(["I4", "I7", "I8", "I16", "I19", "I23", "I26", "I28"]),
  cashflow: new Set(["C4", "C7", "C13", "C20", "C27", "C29"]),
  balance: new Set(["B8", "B11", "B20", "B25", "B33", "B34"]),
  profit_use: new Set(["P3", "P7"]),
};
