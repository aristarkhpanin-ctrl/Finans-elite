import { useQuery } from "@tanstack/react-query";
import { httpDetail } from "../api/client";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { defaultPeriod, type Period } from "../aggregate";
import { efficiencyCards, foreignCards, valuationCards } from "../metricCards";
import { calculateProject } from "../api/calc";
import { getProject } from "../api/projects";
import { IconPrint } from "../components/icons";
import { PlanFactView } from "../components/PlanFactView";
import { printPageCount, PrintReport } from "../components/PrintReport";
import { ReleaseNote } from "../components/ReleaseNote";
import { ReviewBanner } from "../components/ReviewBanner";
import { RatiosView } from "../components/RatiosView";
import { ResultCharts } from "../components/ResultCharts";
import {
  CalcWarnings, isStatementTab, MetricCards, RESULT_TAB_LABELS, ResultTabs, StatementPanel, SummaryExtras,
} from "../components/ResultBlocks";
import { ShareLinks } from "../components/ShareLinks";
import { StatementTable } from "../components/StatementTable";
import { SummaryView } from "../components/SummaryView";
import { useToast } from "../components/Toast";
import { Button, ErrorState, Skeleton } from "../components/ui";
import { downloadBusinessPlanDocx, downloadCsv, downloadPdf, downloadXlsx, statementsToCsv } from "../export";
import { Comments } from "../components/Comments";
import { plural } from "../format";
import { usePageTitle } from "../pageTitle";

export function ProjectResultsPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [tab, setTab] = useState<string>("summary");
  const [printMode, setPrintMode] = useState(false);
  // Режим печати прячет кнопку, которая его открыла: фокус уходит на панель печати, а по
  // выходе возвращается на «Печать» — иначе он падал в никуда, и следующий Tab начинался
  // с начала страницы (найдено клавиатурным обходом, пакет J). Esc — выход, как у модалок.
  const printBarRef = useRef<HTMLDivElement>(null);
  const printOpenRef = useRef<HTMLButtonElement>(null);
  const wasPrinting = useRef(false);
  useEffect(() => {
    if (printMode) printBarRef.current?.querySelector("button")?.focus();
    else if (wasPrinting.current) printOpenRef.current?.focus();
    wasPrinting.current = printMode;
    if (!printMode) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setPrintMode(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [printMode]);
  // Период отображения отчётов (пакет №6): null → авто по горизонту (defaultPeriod).
  const [period, setPeriod] = useState<Period | null>(null);
  const [shareOpen, setShareOpen] = useState(false);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["calc", id],
    queryFn: () => calculateProject(id),
    retry: false,
  });
  const projectQuery = useQuery({ queryKey: ["project", id], queryFn: () => getProject(id) });

  const title = projectQuery.data?.name ?? "";
  usePageTitle("Результаты", title);

  const header = (
    <div className="rhead">
      <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0, flex: 1 }}>
        <button type="button" className="back-btn" onClick={() => navigate(`/projects/${id}`)}>
          ←<span style={{ marginLeft: 6 }}>Редактор</span>
        </button>
        <div style={{ minWidth: 0 }}>
          <h1 className="rhead__title">Результаты</h1>
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
            <button type="button" ref={printOpenRef} onClick={() => setPrintMode(true)}>
              <IconPrint size={15} />
              <span style={{ marginLeft: 6 }}>Печать</span>
            </button>
            {/* Ссылка для инвестора или банка (L4): снимок плана без входа — вместо DOCX
                по почте, о судьбе которого потом не знает никто. */}
            <button type="button" title="Открыть план по ссылке инвестору или банку"
                    onClick={() => setShareOpen(true)}>
              Поделиться
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
        <ErrorState text="Ошибка расчёта" style={{ marginTop: 24, padding: "48px 24px" }} sub={detail}
                    actions={
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
                    } />
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

  // Печать — в том же периоде, что отчёты на экране; число страниц считает та же функция,
  // что раскладывает листы, — «5 страниц» у 24-месячного проекта были бы неправдой.
  const printPeriod = period ?? defaultPeriod(data.n);
  const pages = printPageCount(data, printPeriod);

  return (
    <div className={printMode ? "print-mode" : ""}>
      <div className="print-toolbar">
        <div style={{ minWidth: 0 }}>
          <div className="print-toolbar__title">Печатная версия · PDF (A4, альбом)</div>
          <div className="print-toolbar__sub">
            {pages} {plural(pages, "страница", "страницы", "страниц")}: титул и сводка + 4
            финансовых отчёта · период — как на экране · печать-дружественные цвета,
            аккуратные переносы.
          </div>
        </div>
        <div className="print-toolbar__actions" ref={printBarRef}>
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

        <h2 className="rsection-label">Показатели эффективности</h2>
        <MetricCards cards={effCards} />
        {m.no_return_metrics_note && (
          // Четыре прочерка подряд без причины читаются как «не посчитали». Причина
          // приходит с сервера — второй её копией экран разошёлся бы с документом.
          <div className="field-note" style={{ marginTop: 8 }}>{m.no_return_metrics_note}</div>
        )}
        <ReleaseNote release={data.working_capital_release} />

        {fxCards.length > 0 && (
          <>
            <h2 className="rsection-label">Показатели во второй валюте ({foreignCode})</h2>
            <MetricCards cards={fxCards} compact />
          </>
        )}

        <h2 className="rsection-label">Оценка бизнеса</h2>
        <MetricCards cards={valCards} compact />

        {tab === "summary" && <ReviewBanner projectId={id} />}

        {tab === "summary" && <SummaryExtras data={data} />}

        <ResultTabs tabs={tabs} active={tab} onSelect={setTab} />

        {tab === "summary" && (
          <>
            <SummaryView result={data} discountRate={discountRate} />
            <CalcWarnings warnings={data.warnings} />
          </>
        )}
        {isStatementTab(tab) && (
          <StatementPanel data={data} which={tab} period={period} onPeriod={setPeriod} onWhich={setTab} />
        )}
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
              title={t.name || "Таблица"}
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

        {/* Обсуждение — **рядом с числами** и привязано к тому разделу, который сейчас
            открыт: вопрос «откуда такая себестоимость» без места через месяц не
            прочитать. Подпись раздела уходит вместе с репликой (D3). */}
        <div style={{ marginTop: 20 }}>
          <Comments subject={{ kind: "project", id }} anchor={`report:${tab}`}
                    anchorLabel={RESULT_TAB_LABELS[tab] ?? tab}
                    title={`Обсуждение: ${RESULT_TAB_LABELS[tab] ?? tab}`} />
        </div>
        <ShareLinks open={shareOpen} onClose={() => setShareOpen(false)} projectId={id} />
      </div>

      <PrintReport data={data} title={title || "Результаты"} model={projectQuery.data?.model}
                   period={printPeriod} />
    </div>
  );
}
