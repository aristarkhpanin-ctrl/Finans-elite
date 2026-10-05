import type { ReactNode } from "react";
import { aggregateStatement, defaultPeriod, periodLabels, type Period } from "../aggregate";
import { type CalcResponse, type StatementOut } from "../api/calc";
import type { ProjectModel } from "../api/model";
import { fmtDateOnly, fmtMillions, fmtTable, percent } from "../format";
import { GRANDS, SUBTOTALS } from "./StatementTable";
import { ScrollRegion } from "./ui";

/**
 * Печатный отчёт (макет «Этап 16»): A4 альбомная — титул со сводкой и 4 финансовых
 * отчёта. Цвета фиксированные («чернильные»), не зависят от темы, поэтому печать
 * одинаково светлая из светлой и тёмной темы.
 *
 * Период — тот, что выбран на экране («Месяц | Квартал | Год»), и свёртка та же
 * (`aggregate.ts`, зеркало DOCX): печать показывает то, что человек видел.
 */

type TableKey = keyof typeof SUBTOTALS;

const TABLE_PAGES: Array<{ key: TableKey; title: string; sub: string }> = [
  { key: "income", title: "Отчёт о прибылях и убытках", sub: "Финансовый результат, ₽" },
  { key: "cashflow", title: "Отчёт о движении денежных средств", sub: "Притоки и оттоки, ₽" },
  { key: "balance", title: "Баланс", sub: "Активы и пассивы на конец периода, ₽" },
  { key: "profit_use", title: "Использование прибыли", sub: "Распределение чистой прибыли, ₽" },
];

const PERIOD_WORDS: Record<Period, string> = {
  month: "помесячно", quarter: "по кварталам", year: "по годам проекта",
};

/**
 * Колонок на листе — не больше 12: под эту ширину сделан макет (66px на колонку).
 * Длинный ряд продолжается на следующем листе, а не сужает колонки: 24 месяца в одну
 * строку давали колонку 33px, и шестизначные числа соседних месяцев наезжали друг на
 * друга (матрица скриншотов P13, G15).
 */
export const PRINT_COLS = 12;

/** Ширина знака печатных чисел: 10px моноширинного шрифта — 0,6 em, с запасом. */
const DIGIT_PX = 6.2;
/** Поля ячейки (8 + 8) и ширина колонки макета. */
const CELL_PAD = 16;
const MIN_CELL = 66;
/** Место под колонки на листе: 1052px полезной ширины A4 минус колонка статей 232px. */
const COLS_PX = 820;

/**
 * Ширина колонки — по **самому длинному числу** отчёта, а не константа: в колонку макета
 * помещается десять знаков, и «(1 234 567)» упиралось в соседа (предел, названный в G15).
 * Колонок на листе — сколько таких помещается, но не больше PRINT_COLS.
 */
export function cellWidth(stmt: StatementOut): number {
  let longest = 0;
  for (const line of stmt.lines)
    for (const v of line.values) longest = Math.max(longest, fmtTable(v).text.length);
  return Math.max(MIN_CELL, Math.ceil(longest * DIGIT_PX + CELL_PAD));
}

export function colsPerSheet(width: number): number {
  return Math.max(1, Math.min(PRINT_COLS, Math.floor(COLS_PX / width)));
}

export interface PrintSheet {
  key: TableKey;
  title: string;
  sub: string;
  /** Отчёт, уже свёрнутый по периоду печати (свёртка — одна на лист). */
  stmt: StatementOut;
  /** Полуинтервал колонок [from, to) свёрнутого отчёта. */
  from: number;
  to: number;
  /** Ширина колонки — одна на все листы отчёта, чтобы продолжение совпадало с началом. */
  cellW: number;
}

/** Листы отчётов по порядку: каждый отчёт — столько листов, сколько нужно его колонкам. */
export function printSheets(data: CalcResponse, period: Period): PrintSheet[] {
  const cols = periodLabels(data.n, period).length;
  return TABLE_PAGES.flatMap((tp) => {
    const stmt = aggregateStatement(data[tp.key], tp.key === "balance" ? "balance" : "flow",
                                    data.n, period);
    const cellW = cellWidth(stmt);
    const per = colsPerSheet(cellW);
    return Array.from({ length: Math.ceil(cols / per) }, (_, k) => (
      { ...tp, stmt, cellW, from: k * per, to: Math.min((k + 1) * per, cols) }
    ));
  });
}

/** Всего страниц документа: титул + листы отчётов. */
export function printPageCount(data: CalcResponse, period: Period): number {
  return 1 + printSheets(data, period).length;
}

function PaperFooter({ page, total }: { page: number; total: number }) {
  return (
    <div className="pr-footer">
      <span>Финанс-Элит · финансовое моделирование</span>
      <span>Конфиденциально</span>
      <span>Страница {page} из {total}</span>
    </div>
  );
}

function TablePage({
  stmt,
  labels,
  from,
  to,
  cellW,
  kind,
  title,
  sub,
  projectName,
  engineVersion,
  dateStr,
  page,
  total,
}: {
  stmt: StatementOut;
  labels: string[];
  from: number;
  to: number;
  cellW: number;
  kind: TableKey;
  title: string;
  sub: string;
  projectName: string;
  engineVersion: string;
  dateStr: string;
  page: number;
  total: number;
}) {
  const months = Array.from({ length: to - from }, (_, i) => from + i);
  const subs = SUBTOTALS[kind];
  const grands = GRANDS[kind];
  return (
    <div className="pr-paper">
      <div className="pr-pagenum">стр. {page} / {total}</div>
      <div className="pr-runhead">
        <span className="pr-runproj">{projectName}</span>
        <span className="pr-runver">
          движок {engineVersion} · {dateStr}
        </span>
      </div>
      <div className="pr-ttitle">{title}</div>
      <div className="pr-tsub">{sub}</div>
      <div className="pr-table">
        <div className="pr-thead">
          <div className="pr-tcorner" style={{ width: 232 }}>
            Статья
          </div>
          {months.map((i) => (
            <div key={i} className="pr-tmonth" style={{ width: cellW }}>
              {labels[i]}
            </div>
          ))}
        </div>
        {stmt.lines.map((l) => {
          const rowKind = grands.has(l.code) ? " pr-trow--grand" : subs.has(l.code) ? " pr-trow--sub" : "";
          return (
            <div key={l.code} className={"pr-trow" + rowKind}>
              <div className="pr-tlabel" style={{ width: 232 }}>
                <span className="pr-tcode">{l.code}</span>
                <span className="pr-tname">{l.label}</span>
              </div>
              {months.map((i) => {
                const f = fmtTable(l.values[i]);
                return (
                  <div
                    key={i}
                    className={"pr-tcell" + (f.kind === "neg" ? " pr-tcell--neg" : f.kind === "zero" ? " pr-tcell--zero" : "")}
                    style={{ width: cellW }}
                  >
                    {f.text}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
      <PaperFooter page={page} total={total} />
    </div>
  );
}

/** Логотип организации на бланке (L9): документ отдают клиенту под её именем. */
export interface PrintBrand {
  /** data URL картинки — с сервера, уже без метаданных файла. */
  src: string;
  /** Название организации — для подписи картинки. */
  name: string;
}

export function PrintReport({
  data,
  title,
  model,
  period,
  brand,
}: {
  data: CalcResponse;
  title: string;
  model?: ProjectModel;
  /** Период отчётов — как на экране; не задан — по горизонту, как и там. */
  period?: Period;
  /** Логотип организации; нет — бланк с маркой платформы, как прежде. */
  brand?: PrintBrand | null;
}) {
  const m = data.metrics;
  const v = data.valuation;
  const npv = Number(m.npv);
  const good = npv > 0;
  const dateStr = new Date().toLocaleDateString("ru-RU");
  const n = data.n;
  const per = period ?? defaultPeriod(n);
  const labels = periodLabels(n, per);
  const sheets = printSheets(data, per);
  const total = 1 + sheets.length;

  const rate = model?.settings.discount_rate_annual;
  const meta: Array<[string, string]> = [
    ["Дата старта", fmtDateOnly(model?.header.start_date)],
    ["Горизонт", `${n} мес.`],
    ["Валюта", "Рубль (₽)"],
    ["Ставка дисконт.", rate ? percent(rate, 1) : "—"],
    ["Версия движка", data.engine_version],
  ];

  const irrNum = m.irr_annual != null ? Number(m.irr_annual) : null;
  const rateNum = rate ? Number(rate) : null;
  type Note = { text: string; tone: "good" | "bad" | "" };
  const eff: Array<{ label: string; value: string; note: Note }> = [
    {
      label: "NPV",
      value: fmtMillions(m.npv, { sign: true, digits: 1 }),
      note: { text: good ? "создаёт стоимость" : "разрушает стоимость", tone: good ? "good" : "bad" },
    },
    {
      label: "IRR",
      value: irrNum != null ? percent(m.irr_annual, 1) : "—",
      note:
        irrNum != null && rateNum != null
          ? { text: irrNum >= rateNum ? `выше ставки ${percent(rate, 0)}` : `ниже ставки ${percent(rate, 0)}`, tone: irrNum >= rateNum ? "good" : "bad" }
          : { text: "годовая доходность", tone: "" },
    },
    {
      label: "PI",
      value: m.pi ? Number(m.pi).toFixed(2).replace(".", ",") : "—",
      note: m.pi ? { text: Number(m.pi) >= 1 ? "> 1 — эффективно" : "< 1 — неэффективно", tone: Number(m.pi) >= 1 ? "good" : "bad" } : { text: "—", tone: "" },
    },
    {
      label: "Срок окупаемости",
      value: m.pb_months != null ? `${m.pb_months} мес` : "> горизонта",
      note: { text: m.pb_months != null ? "в пределах горизонта" : "не окупается", tone: m.pb_months != null ? "good" : "bad" },
    },
    {
      label: "Дисконт. окупаемость",
      value: m.dpb_months != null ? `${m.dpb_months} мес` : "—",
      note: { text: m.dpb_months != null ? "по дисконт. потоку" : "не достигается", tone: "" },
    },
    {
      label: "Потребность в финанс.",
      value: m.peak_financing_need ? fmtMillions(m.peak_financing_need, { digits: 1 }) : "—",
      note: { text: "максимальный дефицит", tone: "" },
    },
  ];

  const val: Array<[string, string | null]> = [
    ["Чистые активы", v.net_assets],
    ["Модель Гордона", v.gordon_value ?? null],
    ["DDM", v.dividend_value ?? null],
    ["По мультипликатору", v.earnings_multiple_value ?? null],
    ["Ликвидационная", v.liquidation_value ?? null],
  ];

  const cell = (label: ReactNode, value: ReactNode, note?: Note, big = true) => (
    <div className="pr-mcell">
      <div className="pr-mlabel">{label}</div>
      <div className={big ? "pr-mval" : "pr-vval"}>{value}</div>
      {note && <div className={"pr-mnote" + (note.tone ? ` pr-mnote--${note.tone}` : "")}>{note.text}</div>}
    </div>
  );

  return (
    <ScrollRegion className="print-report" label="Предпросмотр печати">
      {/* Страница 1 — титул и сводка */}
      <div className="pr-paper">
        <div className="pr-pagenum">стр. 1 / {total}</div>
        <div className="pr-band">
          {brand ? (
            <img className="pr-orglogo" src={brand.src} alt={`Логотип «${brand.name}»`} />
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
              <div className="pr-logo">
                <span />
                <span />
                <span />
              </div>
              <div>
                <div className="pr-brand">Финанс-Элит</div>
                <div className="pr-brand-sub">финансовое моделирование предприятия</div>
              </div>
            </div>
          )}
          <div style={{ textAlign: "right" }}>
            <div className="pr-dockind">Отчёт по финансовой модели</div>
            <div className="pr-docdate">Сформировано {dateStr}</div>
            {/* Под логотипом организации марка платформы не пропадает, а уходит в
                подпись: чем сделан расчёт, читателю знать нужно. */}
            {brand && <div className="pr-docdate">подготовлено в Финанс-Элит</div>}
          </div>
        </div>

        <div className="pr-projname">{title}</div>
        <div className="pr-projsub">Помесячная финансовая модель · базовый сценарий</div>

        <div className="pr-meta">
          {meta.map(([label, value]) => (
            <div key={label} className="pr-meta-cell">
              <div className="pr-meta-label">{label}</div>
              <div className="pr-meta-val">{value}</div>
            </div>
          ))}
        </div>

        <div className={"pr-verdict" + (good ? "" : " pr-verdict--bad")}>
          <div className="pr-verdict-mark">{good ? "✓" : "!"}</div>
          <div style={{ minWidth: 0 }}>
            <div className="pr-verdict-title">
              {good ? "Проект создаёт стоимость" : "Проект разрушает стоимость"}
            </div>
            <div className="pr-verdict-sub">
              {good
                ? `Положительный NPV${rate ? ` при ставке ${percent(rate, 0)}` : ""}${m.pb_months != null ? ", окупаемость в пределах горизонта" : ""}.`
                : `Отрицательный NPV${rate ? ` при ставке ${percent(rate, 0)}` : ""} — дисконтированные оттоки превышают притоки.`}
            </div>
          </div>
        </div>

        <div className="pr-seclabel">Показатели эффективности инвестиций</div>
        <div className="pr-mgrid">{eff.map((e) => <div key={e.label}>{cell(e.label, e.value, e.note)}</div>)}</div>
        {m.no_return_metrics_note && (
          // На бумаге объяснить прочерк особенно важно: спросить автора нельзя.
          <div className="pr-note">{m.no_return_metrics_note}</div>
        )}
        {data.working_capital_release && (
          // Закрытие расчётов последнего месяца (пакет K) — та же строка, что на экране и
          // в документе: читатель бумаги должен знать, из чего сложен скачок потока.
          <div className="pr-note">{data.working_capital_release.note}</div>
        )}

        <div className="pr-seclabel">Оценка стоимости бизнеса</div>
        <div className="pr-vgrid">
          {val.map(([label, value]) => (
            <div key={label}>{cell(label, value ? fmtMillions(value, { digits: 1 }) : "—", undefined, false)}</div>
          ))}
        </div>

        <PaperFooter page={1} total={total} />
      </div>

      {/* Дальше — финансовые отчёты, по листу на каждые PRINT_COLS колонок */}
      {sheets.map((s, idx) => {
        // Продолжение называет свой отрезок: лист «М13–М24» без подписи читался бы как
        // тот же отчёт, напечатанный дважды.
        const range = s.to - s.from < labels.length ? ` · ${labels[s.from]}–${labels[s.to - 1]}` : "";
        return (
          <TablePage
            key={`${s.key}-${s.from}`}
            stmt={s.stmt}
            labels={labels}
            from={s.from}
            to={s.to}
            cellW={s.cellW}
            kind={s.key}
            title={s.title}
            sub={`${s.sub} · ${PERIOD_WORDS[per]}${range}`}
            projectName={title}
            engineVersion={data.engine_version}
            dateStr={dateStr}
            page={idx + 2}
            total={total}
          />
        );
      })}
    </ScrollRegion>
  );
}
