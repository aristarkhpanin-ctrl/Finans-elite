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

  return (
    <div className="ap-root">
      <PageSetup />

      <Sheet page={1} total={2}>
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
      </Sheet>

      <Sheet page={2} total={2}>
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

        <div className="ap-fineprint">
          Документ сформирован автоматически по введённой фактической отчётности.
          Оценки коэффициентов даны против универсальных нормативов, если для дела не
          заданы свои. Заключение не является аудиторским в смысле закона об аудиторской
          деятельности.
        </div>
      </Sheet>
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
