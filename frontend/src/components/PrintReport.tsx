import { type CalcResponse } from "../api/calc";
import { StatementTable, SUBTOTALS } from "./StatementTable";
import { SummaryView } from "./SummaryView";

/** Печатная версия отчёта (видна только при печати / сохранении в PDF). */
export function PrintReport({ data, title }: { data: CalcResponse; title: string }) {
  return (
    <div className="print-only print-report">
      <h1>{title}</h1>
      <p className="muted">
        Финансовая модель · движок {data.engine_version} · {new Date().toLocaleDateString("ru-RU")}
      </p>

      <h2>Ключевые выводы</h2>
      <SummaryView result={data} />

      <h2>Отчёт о прибылях и убытках</h2>
      <StatementTable statement={data.income} n={data.n} subtotals={SUBTOTALS.income} />

      <h2>Кэш-фло</h2>
      <StatementTable statement={data.cashflow} n={data.n} subtotals={SUBTOTALS.cashflow} />

      <h2>Баланс</h2>
      <StatementTable statement={data.balance} n={data.n} subtotals={SUBTOTALS.balance} />

      <h2>Использование прибыли</h2>
      <StatementTable statement={data.profit_use} n={data.n} subtotals={SUBTOTALS.profit_use} />
    </div>
  );
}
