import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { line, type CalcResponse } from "../api/calc";
import { money } from "../format";

const compact = (v: number) =>
  v.toLocaleString("ru-RU", { notation: "compact", maximumFractionDigits: 1 });

export function ResultCharts({ result }: { result: CalcResponse }) {
  const c13 = line(result.cashflow, "C13");
  const c20 = line(result.cashflow, "C20");
  const c29 = line(result.cashflow, "C29");
  const i28 = line(result.income, "I28");

  const data = Array.from({ length: result.n }, (_, i) => ({
    m: `М${i + 1}`,
    operating: Number(c13[i] ?? 0),
    investing: Number(c20[i] ?? 0),
    cash: Number(c29[i] ?? 0),
    profit: Number(i28[i] ?? 0),
  }));

  const tooltip = { formatter: (v: number) => money(String(v)) } as const;

  return (
    <div>
      <div className="chart-card">
        <h3>Денежный поток</h3>
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={data} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="m" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={compact} tick={{ fontSize: 12 }} width={56} />
            <Tooltip {...tooltip} />
            <Legend />
            <Bar dataKey="operating" name="Операционный" fill="#2563eb" />
            <Bar dataKey="investing" name="Инвестиционный" fill="#f59e0b" />
            <Line dataKey="cash" name="Остаток денег" stroke="#16a34a" strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-card">
        <h3>Чистая прибыль</h3>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={data} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="m" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={compact} tick={{ fontSize: 12 }} width={56} />
            <Tooltip {...tooltip} />
            <Bar dataKey="profit" name="Чистая прибыль" fill="#7c3aed" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
