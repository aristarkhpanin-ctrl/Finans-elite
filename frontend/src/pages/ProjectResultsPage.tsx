import { useQuery } from "@tanstack/react-query";
import { httpDetail } from "../api/client";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { aggregateFlowSeries, aggregateStatement, defaultPeriod, periodLabels, type Period } from "../aggregate";
import { efficiencyCards, foreignCards, valuationCards } from "../metricCards";
import { calculateProject } from "../api/calc";
import { getProject } from "../api/projects";
import { HintBadge } from "../components/EditorField";
import { IconPrint } from "../components/icons";
import { PlanFactView } from "../components/PlanFactView";
import { PrintReport } from "../components/PrintReport";
import { ReviewBanner } from "../components/ReviewBanner";
import { RatiosView } from "../components/RatiosView";
import { ResultCharts } from "../components/ResultCharts";
import { GRANDS, StatementTable, SUBTOTALS } from "../components/StatementTable";
import { SummaryView } from "../components/SummaryView";
import { useToast } from "../components/Toast";
import { Button, Skeleton } from "../components/ui";
import { downloadBusinessPlanDocx, downloadCsv, downloadPdf, downloadXlsx, statementsToCsv } from "../export";
import { fmtMillions, percent } from "../format";

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
  tables: "Таблицы",
  plan_fact: "План-факт",
};

export function ProjectResultsPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [tab, setTab] = useState<string>("summary");
  const [printMode, setPrintMode] = useState(false);
  // Период отображения отчётов (пакет №6): null → авто по горизонту (defaultPeriod).
  const [period, setPeriod] = useState<Period | null>(null);

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
            <button
              type="button"
              onClick={async () => {
                toast("Готовим PDF…", { kind: "info" });
                try {
                  await downloadPdf("reports.pdf", data, title);
                  toast("Файл PDF скачан", { kind: "success" });
                } catch {
                  toast("Не удалось сформировать PDF", { kind: "error" });
                }
              }}
            >
              PDF
            </button>
            <button
              type="button"
              title="Документ бизнес-плана: заключение, показатели, разделы и отчёты"
              onClick={async () => {
                toast("Готовим бизнес-план…", { kind: "info" });
                try {
                  await downloadBusinessPlanDocx(id, `${title || "business-plan"}.docx`);
                  toast("Бизнес-план (DOCX) скачан", { kind: "success" });
                } catch {
                  toast("Не удалось сформировать бизнес-план", { kind: "error" });
                }
              }}
            >
              Бизнес-план
            </button>
            <button type="button" onClick={() => setPrintMode(true)}>
              <IconPrint size={15} />
              <span style={{ marginLeft: 6 }}>Печать</span>
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
    const detail: string = httpDetail(error) ?? "Не удалось рассчитать модель.";
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

  const tabs = ["summary", "income", "cashflow", "balance", "ratios", "charts"];
  if (data.user_tables.length > 0) tabs.push("tables");
  if (data.actualized_cashflow) tabs.push("plan_fact");

  // Интерпретация показателей (знак, сравнение со ставкой, «не определено») вынесена
  // в чистый модуль `metricCards.ts` — там же её тесты.
  const effCards = efficiencyCards(m, discountRate);
  const valCards = valuationCards(val);

  // Показатели во второй валюте (gap 1.4): поток пересчитан по курсу, дисконт — своей ставкой.
  const mf = data.metrics_foreign;
  const foreignCode = projectQuery.data?.model.environment.currencies?.[1]?.code ?? "вал.";
  const foreignRate = projectQuery.data?.model.settings.discount_rate_annual_foreign;
  const fxCards = foreignCards(mf, foreignCode, foreignRate);

  const statementView = (key: StatementKey) => {
    const eff = period ?? defaultPeriod(data.n);
    const labels = periodLabels(data.n, eff);
    const agg = aggregateStatement(data[key], key === "balance" ? "balance" : "flow", data.n, eff);
    // Детализация строк (drill-down): слагаемые — потоки, сворачиваются суммами.
    const prefix = key === "income" ? "I" : key === "cashflow" ? "C" : null;
    const details = new Map(
      (data.details ?? [])
        .filter((d) => prefix !== null && d.code.startsWith(prefix))
        .map((d) => [
          d.code,
          d.items.map((i) => ({ name: i.name, values: aggregateFlowSeries(i.values, data.n, eff) })),
        ]),
    );
    const sub =
      eff === "month"
        ? `Помесячно · ${data.n} мес · суммы в ₽`
        : eff === "quarter"
          ? `По кварталам · ${labels.length} кв (${data.n} мес) · суммы в ₽`
          : `По годам проекта · ${labels.length} г. (${data.n} мес) · суммы в ₽`;
    return (
      <>
        <div className="report-head">
          <div style={{ minWidth: 0 }}>
            <div className="report-head__title">{TAB_LABELS[key] ?? STATEMENTS.find(([k]) => k === key)?.[1]}</div>
            <div className="report-head__sub">{sub}</div>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <div className="report-switch" aria-label="Период отображения">
              {(["month", "quarter", "year"] as const).map((p) => (
                <button key={p} type="button" className={eff === p ? "on" : ""} onClick={() => setPeriod(p)}>
                  {p === "month" ? "Месяц" : p === "quarter" ? "Квартал" : "Год"}
                </button>
              ))}
            </div>
            <div className="report-switch">
              {STATEMENTS.map(([k, label]) => (
                <button key={k} type="button" className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <StatementTable statement={agg} n={labels.length} subtotals={SUBTOTALS[key]}
                        grands={GRANDS[key]} labels={labels} details={details} />
      </>
    );
  };

  return (
    <div className={printMode ? "print-mode" : ""}>
      <div className="print-toolbar">
        <div style={{ minWidth: 0 }}>
          <div className="print-toolbar__title">Печатная версия · PDF (A4, альбом)</div>
          <div className="print-toolbar__sub">
            5 страниц: титул и сводка + 4 финансовых отчёта · печать-дружественные цвета,
            аккуратные переносы.
          </div>
        </div>
        <div className="print-toolbar__actions">
          <Button variant="ghost" onClick={() => setPrintMode(false)}>
            ← К результатам
          </Button>
          <Button onClick={() => window.print()}>
            <IconPrint size={15} />
            <span style={{ marginLeft: 7 }}>Печать</span>
          </Button>
        </div>
      </div>

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

        {fxCards.length > 0 && (
          <>
            <div className="rsection-label">Показатели во второй валюте ({foreignCode})</div>
            <div className="metric-grid metric-grid--val">
              {fxCards.map((c) => (
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
          </>
        )}

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

        {tab === "summary" && <ReviewBanner projectId={id} />}

        {tab === "summary" && data.product_margins.products.length > 0 && (
          <>
            <div className="rsection-label">Маржа по продуктам (рецептура)</div>
            <div className="contrib-wrap">
              <div className="contrib-row contrib-row--head">
                <div className="contrib-label">Продукт</div>
                <div className="contrib-cell">Выручка</div>
                <div className="contrib-cell">Материалы</div>
                <div className="contrib-cell">Сдельная ЗП</div>
                <div className="contrib-cell">Маржа</div>
                <div className="contrib-cell">Маржа, %</div>
              </div>
              {data.product_margins.products.map((p) => {
                const neg = Number(p.margin) < 0;
                return (
                  <div className="contrib-row" key={p.product_id}>
                    <div className="contrib-label">{p.name || p.product_id}</div>
                    <div className="contrib-cell">{fmtMillions(p.revenue, { digits: 2 })}</div>
                    <div className="contrib-cell">{fmtMillions(p.bom_cost, { digits: 2 })}</div>
                    <div className="contrib-cell">{fmtMillions(p.piece_wages, { digits: 2 })}</div>
                    <div className={"contrib-cell" + (neg ? " contrib-cell--neg" : "")}>
                      {fmtMillions(p.margin, { sign: true, digits: 2 })}
                    </div>
                    <div className={"contrib-cell" + (neg ? " contrib-cell--neg" : "")}>
                      {p.margin_share != null ? percent(p.margin_share, 1) : "—"}
                    </div>
                  </div>
                );
              })}
            </div>
            {Number(data.product_margins.unallocated_direct) > 0 && (
              <div className="field-note" style={{ marginTop: 8 }}>
                Суммовые прямые издержки {fmtMillions(data.product_margins.unallocated_direct, { digits: 2 })} не
                распределяются по продуктам (заданы без рецептуры).
              </div>
            )}
          </>
        )}

        {tab === "summary" && (data.division_margins ?? []).length > 0 && (
          <>
            <div className="rsection-label">Доходы подразделений</div>
            <div className="contrib-wrap">
              <div className="contrib-row contrib-row--head">
                <div className="contrib-label">Подразделение</div>
                <div className="contrib-cell">Выручка</div>
                <div className="contrib-cell">Материалы</div>
                <div className="contrib-cell">Сдельная ЗП</div>
                <div className="contrib-cell">Маржа</div>
                <div className="contrib-cell">Маржа, %</div>
              </div>
              {data.division_margins.map((d) => {
                const neg = Number(d.margin) < 0;
                return (
                  <div className="contrib-row" key={d.division_id}>
                    <div className="contrib-label">
                      {d.name || d.division_id}
                      <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>· {d.product_count} прод.</span>
                    </div>
                    <div className="contrib-cell">{fmtMillions(d.revenue, { digits: 2 })}</div>
                    <div className="contrib-cell">{fmtMillions(d.bom_cost, { digits: 2 })}</div>
                    <div className="contrib-cell">{fmtMillions(d.piece_wages, { digits: 2 })}</div>
                    <div className={"contrib-cell" + (neg ? " contrib-cell--neg" : "")}>
                      {fmtMillions(d.margin, { sign: true, digits: 2 })}
                    </div>
                    <div className={"contrib-cell" + (neg ? " contrib-cell--neg" : "")}>
                      {d.margin_share != null ? percent(d.margin_share, 1) : "—"}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="field-note" style={{ marginTop: 8 }}>
              Свёртка маржи продуктов по бизнес-единицам; продукты без рецептуры/подразделения в свёртку не входят.
            </div>
          </>
        )}

        {tab === "summary" && (data.participants ?? []).length > 0 && (
          <>
            <div className="rsection-label">Доходы участников финансирования</div>
            <div className="contrib-wrap">
              <div className="contrib-row contrib-row--head">
                <div className="contrib-label">Участник</div>
                <div className="contrib-cell">Вложено</div>
                <div className="contrib-cell">Получено</div>
                <div className="contrib-cell">NPV</div>
                <div className="contrib-cell">IRR</div>
                <div className="contrib-cell">IRR с уч. остатка</div>
              </div>
              {data.participants.map((p) => {
                const neg = Number(p.npv_with_terminal ?? p.npv) < 0;
                return (
                  <div className="contrib-row" key={p.id}>
                    <div className="contrib-label">
                      {p.name}
                      {p.kind === "lender" && <span className="fin2-code" style={{ marginLeft: 6 }}>заём</span>}
                    </div>
                    <div className="contrib-cell">{fmtMillions(p.invested, { digits: 2 })}</div>
                    <div className="contrib-cell">{fmtMillions(p.withdrawn, { digits: 2 })}</div>
                    <div className={"contrib-cell" + (neg ? " contrib-cell--neg" : "")}>
                      {fmtMillions(p.npv_with_terminal ?? p.npv, { sign: true, digits: 2 })}
                    </div>
                    <div className="contrib-cell">
                      {p.irr_annual != null ? percent(p.irr_annual, 1) : "—"}
                    </div>
                    <div className="contrib-cell">
                      {p.irr_with_terminal_annual != null ? percent(p.irr_with_terminal_annual, 1) : "—"}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="field-note" style={{ marginTop: 8 }}>
              NPV и «IRR с уч. остатка» — с условным возвратом на конец горизонта: акционерам —
              собственного капитала (B33), кредиторам — непогашенного тела займа.
            </div>
          </>
        )}

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
        {tab === "tables" && data.user_tables.map((t) => (
          <div key={t.id} style={{ marginBottom: 22 }}>
            <div className="report-head">
              <div style={{ minWidth: 0 }}>
                <div className="report-head__title">{t.name || "Таблица"}</div>
                <div className="report-head__sub">Таблица пользователя · формулы над результатом</div>
              </div>
            </div>
            {t.rows.some((r) => r.error) && (
              <div className="warn-banner" style={{ marginBottom: 12 }}>
                <span className="warn-banner__ico">⚠</span>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="warn-banner__title">Ошибки формул</div>
                  {t.rows.filter((r) => r.error).map((r, i) => (
                    <div key={i} className="warn-banner__item">
                      <span className="warn-banner__dot" />
                      {r.name}: {r.error}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <StatementTable
              statement={{ lines: t.rows.map((r, i) => ({ code: String(i + 1), label: r.name, values: r.values })) }}
              n={data.n}
              subtotals={new Set()}
            />
          </div>
        ))}
        {tab === "plan_fact" && data.actualized_cashflow && (
          <PlanFactView
            result={data}
            factUntil={projectQuery.data?.model.actualization.actual_until ?? data.n - 1}
          />
        )}
      </div>

      <PrintReport data={data} title={title || "Результаты"} model={projectQuery.data?.model} />
    </div>
  );
}
