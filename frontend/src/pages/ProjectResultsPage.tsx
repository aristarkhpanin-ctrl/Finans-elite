import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { calculateProject } from "../api/calc";
import { getProject } from "../api/projects";
import { HintBadge } from "../components/EditorField";
import { IconPrint } from "../components/icons";
import { PrintReport } from "../components/PrintReport";
import { RatiosView } from "../components/RatiosView";
import { ResultCharts } from "../components/ResultCharts";
import { GRANDS, StatementTable, SUBTOTALS } from "../components/StatementTable";
import { SummaryView } from "../components/SummaryView";
import { useToast } from "../components/Toast";
import { Button, Skeleton } from "../components/ui";
import { downloadCsv, downloadXlsx, statementsToCsv } from "../export";
import { fmtMillions, fmtRatio, percent } from "../format";

const STATEMENTS = [
  ["income", "Прибыли и убытки"],
  ["cashflow", "Кэш-фло"],
  ["balance", "Баланс"],
  ["profit_use", "Использование прибыли"],
] as const;

type StatementKey = (typeof STATEMENTS)[number][0];

const TAB_LABELS: Record<string, string> = {
  summary: "Сводка",
  income: "Прибыли и убытки",
  cashflow: "Кэш-фло",
  balance: "Баланс",
  ratios: "Коэффициенты",
  charts: "Графики",
  plan_fact: "План-факт",
};

export function ProjectResultsPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [tab, setTab] = useState<string>("summary");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["calc", id],
    queryFn: () => calculateProject(id),
    retry: false,
  });
  const projectQuery = useQuery({ queryKey: ["project", id], queryFn: () => getProject(id) });

  const title = projectQuery.data?.name ?? "";
  const isStatement = STATEMENTS.some(([k]) => k === tab);

  const header = (
    <div className="rhead">
      <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0, flex: 1 }}>
        <button type="button" className="back-btn" onClick={() => navigate(`/projects/${id}`)}>
          ←<span style={{ marginLeft: 6 }}>Редактор</span>
        </button>
        <div style={{ minWidth: 0 }}>
          <div className="rhead__title">Результаты</div>
          {title && <div className="rhead__sub">{title}</div>}
        </div>
      </div>
      <div className="rhead__actions">
        {data && <span className="version-chip">движок {data.engine_version}</span>}
        {data && (
          <div className="export-group">
            <button
              type="button"
              onClick={() => {
                downloadCsv("reports.csv", statementsToCsv(data));
                toast("Файл CSV скачан", { kind: "success" });
              }}
            >
              CSV
            </button>
            <button
              type="button"
              onClick={async () => {
                toast("Готовим XLSX…", { kind: "info" });
                await downloadXlsx("reports.xlsx", data);
                toast("Файл XLSX скачан", { kind: "success" });
              }}
            >
              XLSX
            </button>
            <button type="button" onClick={() => window.print()}>
              <IconPrint size={15} />
              <span style={{ marginLeft: 6 }}>Печать / PDF</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div className="screen-only">
        {header}
        <div className="calc-bar">
          <span className="save-spinner" />
          <span className="calc-bar__text">Идёт расчёт модели…</span>
          <span className="calc-bar__sub">помесячный пересчёт 4 отчётов и показателей</span>
        </div>
        <div className="metric-grid">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} height={92} style={{ borderRadius: 13 }} />
          ))}
        </div>
        <Skeleton height={40} style={{ borderRadius: 10, margin: "18px 0" }} />
        <div className="verdict-grid">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} height={130} style={{ borderRadius: 14 }} />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    const detail: string = (error as any)?.response?.data?.detail ?? "Не удалось рассчитать модель.";
    const balanceIssue = /баланс/i.test(detail);
    return (
      <div className="screen-only">
        {header}
        <div className="error-state" style={{ marginTop: 24, padding: "48px 24px" }}>
          <div className="error-state__ico">!</div>
          <div className="error-state__title">Ошибка расчёта</div>
          <div className="page-sub" style={{ maxWidth: 480, textAlign: "center" }}>
            {detail}
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
            <Button variant="ghost" onClick={() => navigate(`/projects/${id}`)}>
              ← К редактору
            </Button>
            {balanceIssue && (
              <Button onClick={() => navigate(`/projects/${id}?tab=currency`)}>
                Открыть «Валюта и старт»
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const m = data.metrics;
  const val = data.valuation;
  const discountRate = projectQuery.data?.model.settings.discount_rate_annual;
  const rate = discountRate ? Number(discountRate) : null;
  const irr = m.irr_annual !== null && m.irr_annual !== undefined ? Number(m.irr_annual) : null;
  const npv = Number(m.npv);

  const tabs = ["summary", "income", "cashflow", "balance", "ratios", "charts"];
  if (data.actualized_cashflow) tabs.push("plan_fact");

  const effCards: Array<{ label: string; value: string; sub: string; tone: string; hint: string }> = [
    {
      label: "NPV",
      value: fmtMillions(m.npv, { sign: true, digits: 1 }),
      sub: npv > 0 ? "Создаёт стоимость" : npv < 0 ? "Разрушает стоимость" : "На грани",
      tone: npv > 0 ? "good" : npv < 0 ? "bad" : "warn",
      hint: "Чистая приведённая стоимость — сумма дисконтированных денежных потоков. Положительная — проект создаёт стоимость.",
    },
    {
      label: "IRR",
      value: irr !== null ? percent(m.irr_annual, 1) : "—",
      sub:
        irr === null
          ? "Не определена"
          : rate !== null
            ? irr >= rate
              ? `Выше ставки ${percent(discountRate, 0)}`
              : `Ниже ставки ${percent(discountRate, 0)}`
            : "Годовая доходность",
      tone: irr === null ? "" : rate === null || irr >= rate ? "good" : "bad",
      hint: "Внутренняя норма доходности — ставка, при которой NPV = 0. Сравнивается со ставкой дисконтирования.",
    },
    {
      label: "PI",
      value: m.pi ? fmtRatio(m.pi, 2) : "—",
      sub: m.pi == null ? "—" : Number(m.pi) >= 1 ? "> 1 — эффективно" : "< 1 — неэффективно",
      tone: m.pi == null ? "" : Number(m.pi) >= 1 ? "good" : "bad",
      hint: "Индекс прибыльности — отношение дисконтированных притоков к вложениям.",
    },
    {
      label: "Срок окупаемости",
      value: m.pb_months != null ? `${m.pb_months} мес` : "> горизонта",
      sub: m.pb_months != null ? "В пределах горизонта" : "Не окупается",
      tone: m.pb_months != null ? "good" : "bad",
      hint: "Месяц, когда накопленный денежный поток становится положительным.",
    },
    {
      label: "Дисконт. окупаемость",
      value: m.dpb_months != null ? `${m.dpb_months} мес` : "—",
      sub: m.dpb_months != null ? "По дисконт. потоку" : "Не достигается",
      tone: m.dpb_months != null ? "good" : m.pb_months != null ? "warn" : "bad",
      hint: "То же по дисконтированному потоку — учитывает стоимость денег во времени.",
    },
    {
      label: "Потребность в финанс.",
      value: m.peak_financing_need ? fmtMillions(m.peak_financing_need, { digits: 1 }) : "—",
      sub: m.pv_investments
        ? `PV инвестиций ${fmtMillions(m.pv_investments, { digits: 1 })}`
        : "Максимальный дефицит",
      tone: "",
      hint: "Приведённая пиковая потребность в деньгах до выхода проекта в плюс.",
    },
  ];

  const valCards: Array<{ label: string; value: string; hint: string }> = [
    { label: "Чистые активы", value: fmtMillions(val.net_assets, { digits: 1 }), hint: "Активы минус обязательства на конец горизонта." },
    { label: "Модель Гордона", value: val.gordon_value ? fmtMillions(val.gordon_value, { digits: 1 }) : "—", hint: "Капитализация бессрочного потока: CF·(1+g)/(r−g). Не считается при g ≥ ставки." },
    { label: "DDM", value: val.dividend_value ? fmtMillions(val.dividend_value, { digits: 1 }) : "—", hint: "Капитализация дивидендов по модели Гордона." },
    { label: "По мультипликатору", value: val.earnings_multiple_value ? fmtMillions(val.earnings_multiple_value, { digits: 1 }) : "—", hint: "Годовая чистая прибыль × заданный множитель (P/E-подход)." },
    { label: "Ликвидационная", value: val.liquidation_value ? fmtMillions(val.liquidation_value, { digits: 1 }) : "—", hint: "Возвратная стоимость активов при ликвидации минус обязательства." },
  ];

  const statementView = (key: StatementKey) => (
    <>
      <div className="report-head">
        <div style={{ minWidth: 0 }}>
          <div className="report-head__title">{TAB_LABELS[key] ?? STATEMENTS.find(([k]) => k === key)?.[1]}</div>
          <div className="report-head__sub">Помесячный отчёт · {data.n} мес · суммы в ₽</div>
        </div>
        <div className="report-switch">
          {STATEMENTS.map(([k, label]) => (
            <button key={k} type="button" className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <StatementTable statement={data[key]} n={data.n} subtotals={SUBTOTALS[key]} grands={GRANDS[key]} />
    </>
  );

  return (
    <div>
      <div className="screen-only">
        {header}
        <div style={{ height: 4 }} />

        {data.warnings.length > 0 && tab === "summary" && (
          <div className="warn-banner" style={{ marginTop: 16 }}>
            <span className="warn-banner__ico">⚠</span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="warn-banner__title">Предупреждения расчёта ({data.warnings.length})</div>
              {data.warnings.map((w, i) => (
                <div key={i} className="warn-banner__item">
                  <span className="warn-banner__dot" />
                  {w}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="rsection-label">Показатели эффективности</div>
        <div className="metric-grid">
          {effCards.map((c) => (
            <div key={c.label} className="metric-card2">
              <div className="metric-card2__top">
                <span className="metric-card2__label">{c.label}</span>
                <HintBadge text={c.hint} />
              </div>
              <div className={"metric-card2__value" + (c.tone ? ` metric-card2__value--${c.tone}` : "")}>
                {c.value}
              </div>
              <div className="metric-card2__sub">{c.sub}</div>
            </div>
          ))}
        </div>

        <div className="rsection-label">Оценка бизнеса</div>
        <div className="metric-grid metric-grid--val">
          {valCards.map((c) => (
            <div key={c.label} className="metric-card2">
              <div className="metric-card2__top">
                <span className="metric-card2__label" style={{ fontSize: 11.5 }}>
                  {c.label}
                </span>
                <HintBadge text={c.hint} />
              </div>
              <div className="metric-card2__value" style={{ fontSize: 17 }}>
                {c.value}
              </div>
            </div>
          ))}
        </div>

        <div className="etabs-wrap" style={{ margin: "20px 0", borderTop: "1px solid var(--border)", background: "none", padding: 0 }}>
          <div className="etabs fe-scroll">
            {tabs.map((key) => (
              <button
                key={key}
                type="button"
                className={"etab" + (tab === key || (isStatement && key === tab) ? " etab--active" : "")}
                onClick={() => setTab(key)}
              >
                {TAB_LABELS[key]}
              </button>
            ))}
          </div>
        </div>

        {tab === "summary" && (
          <>
            <SummaryView result={data} discountRate={discountRate} />
            {data.warnings.length > 0 && (
              <div className="warn-block">
                <div className="warn-block__head">
                  <span style={{ color: "var(--warn)" }}>⚠</span>Замечания по расчёту
                </div>
                {data.warnings.map((w, i) => (
                  <div key={i} className="warn-block__row">
                    <span className="warn-banner__dot" />
                    <span className="warn-block__text">{w}</span>
                    <span className="level-chip level-chip--warn">предупр.</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
        {isStatement && statementView(tab as StatementKey)}
        {tab === "ratios" && <RatiosView ratios={data.ratios} breakEven={data.break_even} n={data.n} />}
        {tab === "charts" && <ResultCharts result={data} />}
        {tab === "plan_fact" && data.actualized_cashflow && (
          <div>
            <div className="report-head">
              <div style={{ minWidth: 0 }}>
                <div className="report-head__title">План-факт</div>
                <div className="report-head__sub">Кэш-фло с фактом за прошедшие периоды</div>
              </div>
            </div>
            <StatementTable
              statement={data.actualized_cashflow}
              n={data.n}
              subtotals={SUBTOTALS.cashflow}
              grands={GRANDS.cashflow}
            />
            {data.cashflow_variance && (
              <>
                <div className="report-head" style={{ marginTop: 20 }}>
                  <div className="report-head__title" style={{ fontSize: 16 }}>
                    Отклонение (факт − план)
                  </div>
                </div>
                <StatementTable
                  statement={data.cashflow_variance}
                  n={data.n}
                  subtotals={SUBTOTALS.cashflow}
                  grands={GRANDS.cashflow}
                />
              </>
            )}
          </div>
        )}
      </div>

      <PrintReport data={data} title={title || "Результаты"} />
    </div>
  );
}
