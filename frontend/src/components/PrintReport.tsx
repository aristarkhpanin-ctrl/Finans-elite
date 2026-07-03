import type { ReactNode } from "react";
import { type CalcResponse, type StatementOut } from "../api/calc";
import type { ProjectModel } from "../api/model";
import { fmtMillions, fmtTable, percent } from "../format";
import { GRANDS, SUBTOTALS } from "./StatementTable";

/**
 * Печатный отчёт (макет «Этап 16»): A4 альбомная, 5 страниц — титул со сводкой
 * и 4 финансовых отчёта. Цвета фиксированные («чернильные»), не зависят от темы,
 * поэтому печать одинаково светлая из светлой и тёмной темы.
 */

const TABLE_PAGES: Array<{ key: keyof typeof SUBTOTALS; title: string; sub: string }> = [
  { key: "income", title: "Отчёт о прибылях и убытках", sub: "Помесячный финансовый результат, ₽" },
  { key: "cashflow", title: "Отчёт о движении денежных средств", sub: "Притоки и оттоки по месяцам, ₽" },
  { key: "balance", title: "Баланс", sub: "Активы и пассивы на конец каждого месяца, ₽" },
  { key: "profit_use", title: "Использование прибыли", sub: "Распределение чистой прибыли, ₽" },
];

function PaperFooter({ page }: { page: number }) {
  return (
    <div className="pr-footer">
      <span>Финанс-Элит · финансовое моделирование</span>
      <span>Конфиденциально</span>
      <span>Страница {page} из 5</span>
    </div>
  );
}

function TablePage({
  stmt,
  n,
  cellW,
  kind,
  title,
  sub,
  projectName,
  engineVersion,
  dateStr,
  page,
}: {
  stmt: StatementOut;
  n: number;
  cellW: number;
  kind: keyof typeof SUBTOTALS;
  title: string;
  sub: string;
  projectName: string;
  engineVersion: string;
  dateStr: string;
  page: number;
}) {
  const months = Array.from({ length: n }, (_, i) => i);
  const subs = SUBTOTALS[kind];
  const grands = GRANDS[kind];
  return (
    <div className="pr-paper">
      <div className="pr-pagenum">стр. {page} / 5</div>
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
              М{i + 1}
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
      <PaperFooter page={page} />
    </div>
  );
}

export function PrintReport({
  data,
  title,
  model,
}: {
  data: CalcResponse;
  title: string;
  model?: ProjectModel;
}) {
  const m = data.metrics;
  const v = data.valuation;
  const npv = Number(m.npv);
  const good = npv > 0;
  const dateStr = new Date().toLocaleDateString("ru-RU");
  const n = data.n;
  // Ширина колонки под число месяцев (альбомный A4, метка 232px)
  const cellW = Math.max(30, Math.min(66, Math.floor(800 / n)));

  const rate = model?.settings.discount_rate_annual;
  const meta: Array<[string, string]> = [
    ["Дата старта", model?.header.start_date ? new Date(model.header.start_date).toLocaleDateString("ru-RU") : "—"],
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
    ["Модель Гордона", v.gordon_value],
    ["DDM", v.dividend_value],
    ["По мультипликатору", v.earnings_multiple_value],
    ["Ликвидационная", v.liquidation_value],
  ];

  const cell = (label: ReactNode, value: ReactNode, note?: Note, big = true) => (
    <div className="pr-mcell">
      <div className="pr-mlabel">{label}</div>
      <div className={big ? "pr-mval" : "pr-vval"}>{value}</div>
      {note && <div className={"pr-mnote" + (note.tone ? ` pr-mnote--${note.tone}` : "")}>{note.text}</div>}
    </div>
  );

  return (
    <div className="print-report">
      {/* Страница 1 — титул и сводка */}
      <div className="pr-paper">
        <div className="pr-pagenum">стр. 1 / 5</div>
        <div className="pr-band">
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
          <div style={{ textAlign: "right" }}>
            <div className="pr-dockind">Отчёт по финансовой модели</div>
            <div className="pr-docdate">Сформировано {dateStr}</div>
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

        <div className="pr-seclabel">Оценка стоимости бизнеса</div>
        <div className="pr-vgrid">
          {val.map(([label, value]) => (
            <div key={label}>{cell(label, value ? fmtMillions(value, { digits: 1 }) : "—", undefined, false)}</div>
          ))}
        </div>

        <PaperFooter page={1} />
      </div>

      {/* Страницы 2–5 — финансовые отчёты */}
      {TABLE_PAGES.map((tp, idx) => (
        <TablePage
          key={tp.key}
          stmt={data[tp.key]}
          n={n}
          cellW={cellW}
          kind={tp.key}
          title={tp.title}
          sub={tp.sub}
          projectName={title}
          engineVersion={data.engine_version}
          dateStr={dateStr}
          page={idx + 2}
        />
      ))}
    </div>
  );
}
