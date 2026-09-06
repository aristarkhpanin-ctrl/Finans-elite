import { useEffect } from "react";
import type { AuditAnalysis, ReportingStandard } from "../api/audit";
import { REPORTING_STANDARDS } from "../api/audit";
import { plural } from "../format";

/**
 * Печатное заключение «Финанс-Аудит» (макет «Экран 5» и `Заключение (печать).dc.html`).
 *
 * Два листа A4 книжной ориентации, поля 15 / 16 / 11 мм. Бумага **не зависит от темы
 * интерфейса**: палитра печати задана локальными переменными на самом листе, поэтому
 * из тёмной темы документ выходит такой же белый, как из светлой. Тот же приём, что у
 * печатного отчёта «Элит».
 *
 * Отрицательные значения печатаются **в скобках**, а не с минусом: в бумажном
 * финансовом документе минус теряется при копировании и на плохой печати, скобки — нет.
 */

/** Размер страницы задаётся, пока компонент на экране: у «Элит» лист альбомный. */
function PageSetup() {
  useEffect(() => {
    const style = document.createElement("style");
    style.setAttribute("data-audit-print", "");
    // Правило живёт только вместе с этим экраном — иначе оно перевернуло бы и
    // альбомный отчёт первого продукта, который печатается из другого раздела.
    style.textContent = "@media print { @page { size: A4 portrait; margin: 15mm 16mm 11mm; } }";
    document.head.appendChild(style);
    return () => { style.remove(); };
  }, []);
  return null;
}

const LIGHT_TEXT: Record<string, string> = {
  ok: "Устойчивое положение",
  warning: "Требует внимания",
  risk: "Высокий риск",
};

/** Деньги для бумаги: разряды пробелами, отрицательные — в скобках. */
function money(v: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  const s = Math.abs(n).toLocaleString("ru-RU", { maximumFractionDigits: 0 });
  return n < 0 ? `(${s})` : s;
}

/** Коэффициент: два знака; не определён — прочерк, а не ноль. */
function ratio(v: string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) : "—";
}

/** Доля: два знака процента; не определена — прочерк. */
function percent(v: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n)
    ? (n * 100).toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + "%"
    : "—";
}

function Sheet({ page, total, children }: {
  page: number; total: number; children: React.ReactNode;
}) {
  return (
    <section className="ap-paper">
      <div className="ap-pagenum">{page} / {total}</div>
      {children}
      <div className="ap-footer">
        <span>Финанс-Аудит · анализ фактической отчётности</span>
        <span>Конфиденциально</span>
      </div>
    </section>
  );
}

function Rows({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="ap-block">
      <div className="ap-block__title">{title}</div>
      <table className="ap-table">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <td>{label}</td>
              <td className="ap-num">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AuditPrintReport({
  analysis,
  name,
  industry,
  standard,
}: {
  analysis: AuditAnalysis;
  name: string;
  industry: string;
  standard: ReportingStandard;
}) {
  const last = analysis.n - 1;
  const at = (code: string, from: AuditAnalysis["balance"]) =>
    from.find((l) => l.code === code)?.values[last];
  const standardName =
    REPORTING_STANDARDS.find(([k]) => k === standard)?.[1] ?? standard;
  const period = analysis.periods[last] ?? "—";
  const light = analysis.diagnostics?.light ?? "";

  const summary = analysis.summary;
  const valuation = analysis.valuation;
  const flags = analysis.flags.flags;
  const procedures = analysis.procedures;

  const sheets: React.ReactNode[] = [
    <>
        <header className="ap-band">
          <div>
            <div className="ap-brand">Финанс-Аудит</div>
            <div className="ap-brand-sub">Анализ фактической отчётности</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="ap-dockind">Заключение</div>
            <div className="ap-docdate">{new Date().toLocaleDateString("ru-RU")}</div>
          </div>
        </header>

        <h1 className="ap-subject">{name || "Без названия"}</h1>
        <div className="ap-subject-sub">
          {[industry || "отрасль не указана", standardName,
            `${analysis.n} ${plural(analysis.n, "период", "периода", "периодов")}`,
          ].join(" · ")}
        </div>

        {analysis.diagnostics && (
          <div className={"ap-verdict ap-verdict--" + light}>
            <div>
              <div className="ap-verdict__title">
                {LIGHT_TEXT[light] ?? light}
              </div>
              <div className="ap-verdict__sub">{analysis.diagnostics.summary}</div>
            </div>
            <div className="ap-verdict__period">по данным за {period}</div>
          </div>
        )}

        {/* Вердикт по делу и охват проверки — то же, что в шапке экрана. Охват
            стоит рядом с вердиктом, а не в конце: «проверено 18 из 24» меняет
            чтение вывода, и внизу страницы его прочтут уже после решения. */}
        {summary.state === "ready" && (
          <div className="ap-block">
            <div className="ap-block__title">Вердикт по делу</div>
            <p className="ap-para"><b>{summary.headline}</b></p>
            {summary.detail && <p className="ap-para">{summary.detail}</p>}
            <table className="ap-table">
              <tbody>
                <tr>
                  <td>Флаги</td>
                  <td className="ap-num">
                    {summary.risk_flags} риска · {summary.warning_flags} внимания
                  </td>
                </tr>
                <tr>
                  <td>Оценённое влияние флагов</td>
                  <td className="ap-num">{money(summary.priced_total)}</td>
                </tr>
                <tr>
                  <td>Охват проверки</td>
                  <td className="ap-num">
                    {procedures.total
                      ? `${procedures.closed} из ${procedures.total}`
                        + (procedures.coverage ? ` · ${percent(procedures.coverage)}` : "")
                      : "—"}
                  </td>
                </tr>
              </tbody>
            </table>
            {/* Ровно та же оговорка, что на экране и в DOCX: сумма оценённых
                находок и торг — разные величины. */}
            <p className="ap-fine">
              Оценённое влияние флагов — не скидка к цене.
              {summary.unpriced > 0
                && ` Ещё ${summary.unpriced} ${plural(summary.unpriced, "флаг", "флага", "флагов")}`
                   + " денежной меры не имеют и в сумму не вошли."}
            </p>
          </div>
        )}

        {/* Оговорки печатаются на бумаге, а не только на экране: документ уходит
            из системы и должен нести те же предупреждения, что и результат. */}
        {analysis.revalued && (
          <div className="ap-note">
            Показатели рассчитаны по отчётности <b>с учётом переоценки статей</b> —
            они отличаются от учётных данных.
          </div>
        )}
        {!analysis.balanced && (
          <div className="ap-note ap-note--warn">
            Баланс не сходится: актив ≠ пассив. Структурные коэффициенты искажены.
          </div>
        )}

        <div className="ap-block">
          <div className="ap-block__title">Заключение</div>
          {analysis.opinion.split("\n\n").map((block, i) => (
            <p className="ap-para" key={i}>{block.replace(/\n/g, " ")}</p>
          ))}
        </div>
    </>,

    // Лист находок: реестр флагов, качество прибыли, сверка долга, расчёт цены.
    // Это и есть то, за чем документ несут в инвесткомитет, — до этой фазы всё
    // перечисленное оставалось на экране.
    <>
        <div className="ap-sheet-head">Результаты проверки</div>

        <div className="ap-block">
          <div className="ap-block__title">Реестр красных флагов</div>
          {flags.length === 0 ? (
            <p className="ap-para">
              Правила реестра не сработали ни разу: признаков из каталога на введённой
              отчётности не найдено.
            </p>
          ) : (
            <table className="ap-table">
              <tbody>
                {flags.map((f) => (
                  <tr key={f.code}>
                    <td>{f.title}</td>
                    <td className="ap-zone">
                      {f.severity === "risk" ? "риск" : "внимание"}
                    </td>
                    {/* «Меры нет» — не ноль рублей: флаг существует, суммы у него нет. */}
                    <td className="ap-num">
                      {f.impact === null ? "меры нет" : money(f.impact)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="ap-cols">
          <Rows
            title={`Качество прибыли (${analysis.earnings.base_code})`}
            rows={[
              ["По отчёту", money(analysis.earnings.reported[last])],
              ["Нормализованный", money(analysis.earnings.normalized[last])],
              ["Корректировок", String(analysis.earnings.adjustments.length)],
              ["Оценка", analysis.earnings.grade ?? "не выводится"],
            ]}
          />
          <Rows
            title="Обязательства"
            rows={[
              ["Долг по реестру", money(analysis.obligations.balance_debt)],
              ["Долг по балансу", money(analysis.obligations.reported_debt)],
              ["Расхождение", money(analysis.obligations.discrepancy)],
              // Забалансовое печатается отдельной строкой и не суммируется
              // с долгом: сложение дало бы величину, которой нет ни в одном отчёте.
              ["Забалансовые (не в сумме)", money(analysis.obligations.off_balance)],
            ]}
          />
        </div>

        <div className="ap-block">
          <div className="ap-block__title">Расчёт цены за 100% доли</div>
          {valuation.enterprise_value === null ? (
            <>
              <p className="ap-para">Оценка не посчитана.</p>
              {valuation.blockers.map((b) => (
                <p className="ap-fine" key={b}>{b}</p>
              ))}
            </>
          ) : (
            <>
              <table className="ap-table">
                <tbody>
                  {valuation.bridge.map((b) => (
                    <tr key={b.label}>
                      <td>{b.label}</td>
                      <td className="ap-num">{money(b.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="ap-fine">
                Метод DCF, ставка дисконтирования {percent(valuation.wacc)}, рост в
                постпрогнозе {percent(valuation.terminal_growth)}.
                {valuation.equity_min !== null && valuation.equity_max !== null
                  && ` Диапазон по чувствительности: ${money(valuation.equity_min)} — `
                     + `${money(valuation.equity_max)}.`}
                {valuation.discount !== null
                  && ` Дисконт к цене продавца: ${percent(valuation.discount)}.`}
              </p>
            </>
          )}
        </div>
    </>,

    <>
        <div className="ap-sheet-head">Показатели за {period}</div>

        <div className="ap-cols">
          <Rows
            title="Аналитическая форма"
            rows={[
              ["Суммарный актив", money(at("A_TOTAL", analysis.balance))],
              ["Оборотные активы", money(at("A_CURRENT", analysis.balance))],
              ["Капитал и резервы", money(at("P_EQUITY", analysis.balance))],
              ["Суммарный пассив", money(at("P_TOTAL", analysis.balance))],
              ["Выручка", money(at("I_REVENUE", analysis.income))],
              ["Валовая прибыль", money(at("I_GROSS", analysis.income))],
              ["Операционная прибыль", money(at("I_EBIT", analysis.income))],
              ["Чистая прибыль", money(at("I_NET", analysis.income))],
            ]}
          />
          <Rows
            title="Ключевые коэффициенты"
            rows={Object.entries(analysis.ratios)
              .flatMap(([, series]) => Object.entries(series))
              .filter(([label]) => KEY_RATIOS.includes(label))
              .map(([label, values]) => [label, ratio(values[last])])}
          />
        </div>

        {analysis.diagnostics && analysis.diagnostics.scores.length > 0 && (
          <div className="ap-block">
            <div className="ap-block__title">Модели вероятности банкротства</div>
            <table className="ap-table">
              <tbody>
                {analysis.diagnostics.scores.map((s) => (
                  <tr key={s.id}>
                    <td>{s.name}</td>
                    <td className="ap-num">{ratio(s.values[last])}</td>
                    <td className="ap-zone">{ZONE[s.zones[last] ?? ""] ?? "не рассчитан"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Границы проверки печатаются на бумаге: умолчание о непроверенном
            читатель документа принимает за проверенное. */}
        {procedures.limits.length > 0 && (
          <div className="ap-block">
            <div className="ap-block__title">Границы проверки</div>
            {procedures.limits.map((l) => (
              <p className="ap-fine" key={l}>{l}</p>
            ))}
          </div>
        )}

        <div className="ap-fineprint">
          Документ сформирован автоматически по введённой фактической отчётности.
          Оценки коэффициентов даны против универсальных нормативов, если для дела не
          заданы свои. Заключение не является аудиторским в смысле закона об аудиторской
          деятельности и не является инвестиционной рекомендацией.
        </div>
    </>,
  ];

  return (
    <div className="ap-root">
      <PageSetup />
      {sheets.map((content, i) => (
        // Число листов считается, а не пишется: разделы условны (без оценки лист
        // короче), и «1 / 2» на трёхстраничном документе — ошибка в самом документе.
        <Sheet key={i} page={i + 1} total={sheets.length}>{content}</Sheet>
      ))}
    </div>
  );
}

/** Что печатаем на бумаге: лист один, и на нём должны быть решающие показатели. */
const KEY_RATIOS = [
  "Коэффициент текущей ликвидности",
  "Коэффициент срочной ликвидности",
  "Коэффициент автономии",
  "Суммарные обязательства к активам",
  "Коэффициент покрытия процентов",
  "Рентабельность чистой прибыли",
  "Рентабельность активов (ROA)",
  "Рентабельность собств. капитала (ROE)",
];

const ZONE: Record<string, string> = {
  safe: "устойчивая зона",
  grey: "серая зона",
  distress: "зона риска",
};
