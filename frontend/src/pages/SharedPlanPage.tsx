import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Period } from "../aggregate";
import { httpDetail, httpStatus } from "../api/client";
import { getSharedPlan } from "../api/share";
import { CubeHero } from "../components/CubeHero";
import { applyProduct, PRODUCTS } from "../components/product";
import { RatiosView } from "../components/RatiosView";
import { ReleaseNote } from "../components/ReleaseNote";
import {
  CalcWarnings, isStatementTab, MetricCards, ResultTabs, StatementPanel, SummaryExtras,
} from "../components/ResultBlocks";
import { ResultCharts } from "../components/ResultCharts";
import { SummaryView } from "../components/SummaryView";
import { getTheme, toggleTheme } from "../components/theme";
import { useToast } from "../components/Toast";
import { Button, ErrorState, Loading } from "../components/ui";
import { downloadSharedBusinessPlan } from "../export";
import { efficiencyCards, foreignCards, valuationCards } from "../metricCards";
import { usePageTitle } from "../pageTitle";

/**
 * План по ссылке — для инвестора или банка (пакет L, L4). Страница **без входа**: секрет
 * в адресе и есть пропуск.
 *
 * Показывается **снимок** — версия, которую отправили, а не живая модель. Что это копия,
 * для кого она, до какого числа открыта и что открытие видно отправителю, говорит сервер
 * (`notes`), и эти слова стоят над числами, а не под ними: посетитель должен знать, что
 * смотрит, раньше, чем начнёт смотреть. Разметка блоков — та же, что у владельца
 * (`ResultBlocks`): вторая копия разошлась бы с первой.
 */

const TABS = ["summary", "income", "cashflow", "balance", "ratios", "charts"];

function day(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU");
}

export function SharedPlanPage() {
  const { token = "" } = useParams();
  const toast = useToast();
  const [tab, setTab] = useState("summary");
  const [period, setPeriod] = useState<Period | null>(null);
  const [theme, setTheme] = useState(getTheme());
  const [busy, setBusy] = useState(false);
  // План — бизнес-план, и тема зелёная; память о продукте посетителя не трогаем.
  useEffect(() => applyProduct("business", false), []);

  const query = useQuery({
    queryKey: ["shared", token], queryFn: () => getSharedPlan(token), retry: false,
  });
  const shared = query.data;
  usePageTitle(shared ? `План «${shared.project_name}»` : "План по ссылке");

  const download = async () => {
    if (!shared) return;
    setBusy(true);
    try {
      await downloadSharedBusinessPlan(token, `${shared.project_name || "business-plan"}.docx`);
      toast("Бизнес-план (DOCX) скачан", { kind: "success" });
    } catch (e) {
      toast(httpDetail(e) ?? "Не удалось сформировать бизнес-план", { kind: "error" });
    } finally {
      setBusy(false);
    }
  };

  const product = PRODUCTS.business;
  return (
    <div className="app">
      <header className="shell-header">
        <div className="shell-left">
          <div className="shell-brand">
            <div className="shell-mark">
              <CubeHero accent={product.cubeAccent} backdrop="transparent" showEnvironment={false}
                        showOrbit={false} pointerTilt={false} />
            </div>
            <span className="shell-word">Финанс<span>{product.brand}</span></span>
          </div>
        </div>
        <div className="shell-right">
          <button
            type="button"
            className="icon-btn38"
            aria-label={theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему"}
            onClick={() => setTheme(toggleTheme())}
          >
            <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
          </button>
        </div>
      </header>

      <main className="content" id="content" tabIndex={-1}>
        {query.isLoading && <Loading text="Открываем план…" />}

        {query.isError && (
          <>
            <h1 className="sr-only">План по ссылке</h1>
            <ErrorState
              text={httpStatus(query.error) === 410 ? "Ссылка больше не действует"
                : httpStatus(query.error) === 404 ? "Ссылка не найдена" : "План не открылся"}
              sub={httpDetail(query.error) ?? "Не удалось загрузить план. Попробуйте позже."}
              style={{ marginTop: 24, padding: "48px 24px" }}
              onRetry={httpStatus(query.error) ? undefined : () => void query.refetch()}
            />
          </>
        )}

        {shared && (() => {
          const r = shared.result;
          const m = r.metrics;
          const fx = foreignCards(r.metrics_foreign, shared.foreign_code || "вал.",
                                  shared.discount_rate_annual_foreign);
          return (
            <>
              {/* Своя шапка, а не шапка результатов: там подпись обрезается многоточием, а
                  «копия для кого» — главное, что посетитель должен прочесть целиком. */}
              <div className="shared-head">
                <div className="shared-head__title">
                  <div className="shared-kicker">Бизнес-план · {shared.organization}</div>
                  <h1>{shared.project_name}</h1>
                  <div className="shared-head__for">Копия для: {shared.shared_for}</div>
                </div>
                <div className="shared-head__actions">
                  <span className="version-chip">движок {r.engine_version}</span>
                  <Button variant="ghost" loading={busy} onClick={download}>
                    Бизнес-план (DOCX)
                  </Button>
                </div>
              </div>

              <section className="shared-terms" aria-label="Об этой копии">
                <div className="shared-terms__head">
                  Открыта до {day(shared.expires_at)} · версия «{shared.version_label}» ·
                  отправлена {day(shared.created_at)}
                </div>
                <ul className="share-notes">
                  {shared.notes.map((n) => <li key={n}>{n}</li>)}
                </ul>
              </section>

              <h2 className="rsection-label">Показатели эффективности</h2>
              <MetricCards cards={efficiencyCards(m, shared.discount_rate_annual)} />
              {m.no_return_metrics_note && (
                <div className="field-note" style={{ marginTop: 8 }}>{m.no_return_metrics_note}</div>
              )}
              <ReleaseNote release={r.working_capital_release} />

              {fx.length > 0 && (
                <>
                  <h2 className="rsection-label">Показатели во второй валюте ({shared.foreign_code})</h2>
                  <MetricCards cards={fx} compact />
                </>
              )}

              <h2 className="rsection-label">Оценка бизнеса</h2>
              <MetricCards cards={valuationCards(r.valuation)} compact />

              {tab === "summary" && <SummaryExtras data={r} />}

              <ResultTabs tabs={TABS} active={tab} onSelect={setTab} />

              {tab === "summary" && (
                <>
                  <SummaryView result={r} discountRate={shared.discount_rate_annual} />
                  <CalcWarnings warnings={r.warnings} />
                </>
              )}
              {isStatementTab(tab) && (
                <StatementPanel data={r} which={tab} period={period} onPeriod={setPeriod}
                                onWhich={setTab} />
              )}
              {tab === "ratios" && <RatiosView ratios={r.ratios} breakEven={r.break_even} n={r.n} />}
              {tab === "charts" && <ResultCharts result={r} />}

              <footer className="shared-foot">
                План построен в Финанс-Элит: помесячная модель, четыре отчёта и показатели.{" "}
                <Link to="/register">Построить свой план</Link>
              </footer>
            </>
          );
        })()}
      </main>
    </div>
  );
}
