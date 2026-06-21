import type { RatioGroup, RatiosOut } from "../api/calc";
import { ratio } from "../format";

const GROUPS: [keyof RatiosOut, string][] = [
  ["liquidity", "Ликвидность"],
  ["activity", "Деловая активность"],
  ["gearing", "Структура капитала"],
  ["profitability", "Рентабельность"],
  ["investment", "Инвестиционные (на акцию)"],
];

function GroupTable({ title, group, n }: { title: string; group: RatioGroup; n: number }) {
  const names = Object.keys(group);
  if (names.length === 0) return null;
  const months = Array.from({ length: n }, (_, i) => i + 1);
  return (
    <div style={{ marginBottom: 18 }}>
      <h3 style={{ margin: "0 0 8px", fontSize: 15 }}>{title}</h3>
      <div className="fin-table-wrap">
        <table className="fin-table">
          <thead>
            <tr>
              <th className="label-col">Показатель</th>
              {months.map((m) => (
                <th key={m} className="num">М{m}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {names.map((name) => (
              <tr key={name}>
                <td className="label-col" title={name}>{name}</td>
                {months.map((_, i) => (
                  <td key={i} className="num">{ratio(group[name][i])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function RatiosView({ ratios, n }: { ratios: RatiosOut; n: number }) {
  return (
    <div>
      {GROUPS.map(([key, title]) => (
        <GroupTable key={key} title={title} group={ratios[key]} n={n} />
      ))}
    </div>
  );
}
