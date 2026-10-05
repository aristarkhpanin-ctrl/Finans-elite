import type { CalcResponse } from "../api/calc";
import { fmtMillions, fmtRatio } from "../format";
import { ScrollRegion } from "./ui";

type DebtService = NonNullable<CalcResponse["debt_service"]>;
type DebtYear = DebtService["years"][number];

/** Обычное требование банков к покрытию долга — порог словами (практика, не закон). */
const BANK_DSCR_MIN = 1.2;

/**
 * Оценка покрытия **словами**, а не только цветом: «не покрывает» читается и диктором, и
 * при печати без цвета. Пороги — те же, что у правил ревью; текст оговорки — с сервера.
 */
function coverage(y: DebtYear): { text: string; tone: "" | "neg" | "warn" } {
  if (y.dscr == null) return { text: "платежей нет", tone: "" };
  const v = Number(y.dscr);
  if (v < 1) return { text: "не покрывает платежи", tone: "neg" };
  if (v < BANK_DSCR_MIN) return { text: "ниже требования банков", tone: "warn" };
  return { text: "с запасом", tone: "" };
}

/**
 * Взгляд банка (движок 0.9.58, пакет L): покрытие долга (DSCR) и долговая нагрузка по
 * годам проекта. Первый вопрос кредитора — хватает ли потока на проценты **и тело**;
 * покрытие одних процентов, которое было в коэффициентах, на него не отвечает. Как
 * считается и чего не видно — оговорка с сервера, второй её копии на экране нет.
 */
export function DebtServiceView({ debt }: { debt?: DebtService | null }) {
  if (!debt) return null;
  const short = debt.years.filter((y) => Number(y.shortfall) > 0);
  const skipped = debt.years.filter((y) => y.leverage == null && y.leverage_note);
  return (
    <>
      <h2 className="rsection-label">Обслуживание долга (взгляд банка)</h2>
      {debt.min_dscr != null && (
        <div className="field-note" style={{ marginTop: 4 }}>
          Наименьшее покрытие долга (DSCR) — <b>{fmtRatio(debt.min_dscr)}</b>,{" "}
          {debt.min_dscr_year}.
        </div>
      )}
      <ScrollRegion className="contrib-wrap" label="Обслуживание долга по годам">
        <div className="contrib-row contrib-row--head">
          <div className="contrib-label">Год</div>
          <div className="contrib-cell">Поток для долга</div>
          <div className="contrib-cell">Платежи по долгу</div>
          <div className="contrib-cell">DSCR</div>
          <div className="contrib-cell contrib-cell--wide">Покрытие</div>
          <div className="contrib-cell">Чистый долг</div>
          <div className="contrib-cell">EBITDA</div>
          <div className="contrib-cell">Долг / EBITDA</div>
        </div>
        {debt.years.map((y) => {
          const c = coverage(y);
          const tone = c.tone ? ` contrib-cell--${c.tone}` : "";
          return (
            <div className="contrib-row" key={y.label}>
              <div className="contrib-label">
                {y.label}{y.months < 12 && ` (${y.months} мес.)`}
              </div>
              <div className="contrib-cell">{fmtMillions(y.cfads, { digits: 2 })}</div>
              <div className="contrib-cell">{fmtMillions(y.service, { digits: 2 })}</div>
              <div className={"contrib-cell" + tone}>
                {y.dscr != null ? fmtRatio(y.dscr) : "—"}
              </div>
              <div className={"contrib-cell contrib-cell--wide" + tone}>{c.text}</div>
              <div className="contrib-cell">{fmtMillions(y.net_debt, { digits: 2 })}</div>
              <div className="contrib-cell">{fmtMillions(y.ebitda, { digits: 2 })}</div>
              <div className="contrib-cell">
                {y.leverage != null ? fmtRatio(y.leverage) : "—"}
              </div>
            </div>
          );
        })}
      </ScrollRegion>
      {short.length > 0 && (
        <div className="field-note field-note--warn" style={{ marginTop: 8 }}>
          Платежи больше потока —{" "}
          {short.map((y) => `${y.label}: не хватает ${fmtMillions(y.shortfall, { digits: 2 })}`)
            .join("; ")}. Эти деньги придётся взять не из проекта.
        </div>
      )}
      {skipped.length > 0 && (
        <div className="field-note" style={{ marginTop: 8 }}>
          Долг / EBITDA не считается:{" "}
          {skipped.map((y) => `${y.label} — ${y.leverage_note}`).join("; ")}.
        </div>
      )}
      <div className="field-note" style={{ marginTop: 8 }}>{debt.note}</div>
    </>
  );
}
