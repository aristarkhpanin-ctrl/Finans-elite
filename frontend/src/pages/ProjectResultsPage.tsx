import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { calculateProject } from "../api/calc";
import { getProject } from "../api/projects";
import { PrintReport } from "../components/PrintReport";
import { ResultCharts } from "../components/ResultCharts";
import { RatiosView } from "../components/RatiosView";
import { StatementTable, SUBTOTALS } from "../components/StatementTable";
import { SummaryView } from "../components/SummaryView";
import { ErrorState, Hint, Loading } from "../components/ui";
import { downloadCsv, downloadXlsx, statementsToCsv } from "../export";
import { money, percent } from "../format";

const BASE_TABS: [string, string][] = [
  ["summary", "Сводка"],
  ["income", "Прибыли и убытки"],
  ["cashflow", "Кэш-фло"],
  ["balance", "Баланс"],
  ["ratios", "Коэффициенты"],
  ["charts", "Графики"],
];

export function ProjectResultsPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState<string>("summary");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["calc", id],
    queryFn: () => calculateProject(id),
    retry: false,
  });
  const projectQuery = useQuery({ queryKey: ["project", id], queryFn: () => getProject(id) });

  if (isLoading) return <Loading text="Расчёт…" />;
  if (isError) {
    const detail = (error as any)?.response?.data?.detail;
    return <ErrorState text={`Ошибка расчёта: ${detail || "не удалось рассчитать"}`} />;
  }
  if (!data) return null;

  const m = data.metrics;
  const val = data.valuation;
  const irr = m.irr_annual ? percent(m.irr_annual) : "—";
  const months = (v: number | null) => (v == null ? "—" : `${v} мес.`);
  const tabs: [string, string][] = data.actualized_cashflow
    ? [...BASE_TABS, ["plan_fact", "План-факт"]]
    : BASE_TABS;

  const title = projectQuery.data?.name ?? "Результаты";

  return (
    <div>
      <div className="screen-only">
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <button className="link-btn" onClick={() => navigate(`/projects/${id}`)}>← Редактор</button>
        <span style={{ flex: 1 }} />
        <button className="link-btn" onClick={() => downloadCsv("reports.csv", statementsToCsv(data))}>
          Экспорт CSV
        </button>
        <button className="link-btn" onClick={() => { void downloadXlsx("reports.xlsx", data); }}>
          Экспорт XLSX
        </button>
        <button className="link-btn" onClick={() => window.print()}>Печать / PDF</button>
        <button className="link-btn" onClick={() => navigate(`/projects/${id}/analysis`)}>Анализ</button>
        <span className="muted">движок {data.engine_version}</span>
      </div>
      <h1>Результаты</h1>

      {data.warnings.length > 0 && (
        <div className="warnings">{data.warnings.join("; ")}</div>
      )}

      <div className="metrics">
        <div className="metric"><div className="m-label">NPV<Hint text="Чистая приведённая стоимость: сумма дисконтированных денежных потоков проекта. Больше 0 — проект создаёт стоимость." /></div><div className="m-value">{money(m.npv)}</div></div>
        <div className="metric"><div className="m-label">IRR<Hint text="Внутренняя норма доходности: ставка, при которой NPV = 0. Сравните со ставкой дисконтирования: выше — проект выгоден." /></div><div className="m-value">{irr}</div></div>
        <div className="metric"><div className="m-label">PI<Hint text="Индекс прибыльности: отдача на единицу вложенного капитала. Больше 1 — проект окупает вложения." /></div><div className="m-value">{m.pi ? Number(m.pi).toFixed(2) : "—"}</div></div>
        <div className="metric"><div className="m-label">Срок окупаемости<Hint text="Месяц, в котором накопленный денежный поток до финансирования становится положительным." /></div><div className="m-value">{months(m.pb_months)}</div></div>
        <div className="metric"><div className="m-label">Дисконт. окупаемость<Hint text="Срок окупаемости с учётом дисконтирования (стоимости денег во времени) — обычно дольше обычного." /></div><div className="m-value">{months(m.dpb_months)}</div></div>
        <div className="metric"><div className="m-label">Потребность в финанс.<Hint text="Приведённая пиковая потребность в деньгах: сколько капитала нужно привлечь до выхода проекта в плюс." /></div><div className="m-value">{m.peak_financing_need ? money(m.peak_financing_need) : "—"}</div></div>
      </div>

      <h3 style={{ marginTop: 18, marginBottom: 6 }}>Оценка бизнеса</h3>
      <div className="metrics">
        <div className="metric">
          <div className="m-label">Чистые активы<Hint text="Собственный капитал на конец горизонта (активы минус обязательства, B33)." /></div>
          <div className="m-value">{money(val.net_assets)}</div>
        </div>
        <div className="metric">
          <div className="m-label">По модели Гордона<Hint text="Капитализация бессрочного свободного денежного потока: CF·(1+g)/(r−g), где g — темп роста, r — ставка дисконтирования." /></div>
          <div className="m-value">{val.gordon_value ? money(val.gordon_value) : "—"}</div>
        </div>
        <div className="metric">
          <div className="m-label">DDM (дивиденды)<Hint text="Капитализация дивидендов по модели Гордона: годовые дивиденды · (1+g)/(r−g)." /></div>
          <div className="m-value">{val.dividend_value ? money(val.dividend_value) : "—"}</div>
        </div>
        <div className="metric">
          <div className="m-label">По мультипликатору<Hint text="Годовая чистая прибыль, умноженная на заданный множитель (P/E-подход)." /></div>
          <div className="m-value">{val.earnings_multiple_value ? money(val.earnings_multiple_value) : "—"}</div>
        </div>
        <div className="metric">
          <div className="m-label">Ликвидационная<Hint text="Возвратная стоимость активов при ликвидации (доля возврата · активы) минус обязательства." /></div>
          <div className="m-value">{val.liquidation_value ? money(val.liquidation_value) : "—"}</div>
        </div>
      </div>

      <div className="tabs">
        {tabs.map(([key, label]) => (
          <button key={key} className={`tab ${tab === key ? "tab--active" : ""}`} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "summary" && <SummaryView result={data} />}
      {tab === "income" && <StatementTable statement={data.income} n={data.n} subtotals={SUBTOTALS.income} />}
      {tab === "cashflow" && <StatementTable statement={data.cashflow} n={data.n} subtotals={SUBTOTALS.cashflow} />}
      {tab === "balance" && <StatementTable statement={data.balance} n={data.n} subtotals={SUBTOTALS.balance} />}
      {tab === "ratios" && <RatiosView ratios={data.ratios} n={data.n} />}
      {tab === "charts" && <ResultCharts result={data} />}
      {tab === "plan_fact" && data.actualized_cashflow && (
        <div>
          <h3>Кэш-фло (факт за прошедшие периоды)</h3>
          <StatementTable statement={data.actualized_cashflow} n={data.n} subtotals={SUBTOTALS.cashflow} />
          {data.cashflow_variance && (
            <>
              <h3 style={{ marginTop: 16 }}>Отклонение (факт − план)</h3>
              <StatementTable statement={data.cashflow_variance} n={data.n} subtotals={SUBTOTALS.cashflow} />
            </>
          )}
        </div>
      )}
      </div>

      <PrintReport data={data} title={title} />
    </div>
  );
}
