import type { AuditBenchmarkView } from "../api/audit";
import { fmtDateOnly } from "../format";

/**
 * Сопоставление дела с ориентиром **организации** (SPEC, Прил. Ф).
 *
 * Макеты трижды обещают «сравнение с отраслью», и трижды платформа отказывала: базы
 * сделок у неё нет. Ориентиры организации превращают отказ в функцию — при одном
 * условии: их ни на секунду не выдают за рынок. Поэтому оговорка «это ваш ориентир»
 * печатается **всегда**, а не при отклонении, источник и дата стоят рядом с числом, а
 * отказ (нет ориентира, другая база, нет отрасли, нет оценки) называет причину вместо
 * нулей — «сравнили и сошлось» и «не с чем сравнивать» разные вещи.
 */

const mult = (v: string | null): string =>
  v === null ? "—" : `${Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 2 })}×`;

const share = (v: string): string =>
  `${(Number(v) * 100).toLocaleString("ru-RU", { maximumFractionDigits: 0 })}%`;


export function AuditBenchmark({ view }: { view: AuditBenchmarkView }) {
  const dev = view.deviation === null ? null : Number(view.deviation);
  return (
    <div className="audit-block">
      <div className="audit-block__title">Сравнение с ориентиром организации</div>

      {view.available ? (
        <>
          <div className="bm-row">
            <div className="sum-metric">
              <div className="mini-label">Дело · {view.metric_label}</div>
              <div className="sum-metric__val">{mult(view.case_multiple)}</div>
              <div className="sum-metric__note">подразумеваемый мультипликатор оценки</div>
            </div>
            <div className="sum-metric">
              <div className="mini-label">Ориентир · {view.industry}</div>
              <div className="sum-metric__val">{mult(view.benchmark)}</div>
              <div className="sum-metric__note">
                {view.source || "источник не указан"}
                {view.updated_at && ` · ${fmtDateOnly(view.updated_at)}`}
              </div>
            </div>
            <div className="sum-metric">
              <div className="mini-label">Отклонение</div>
              {/* Ни «дороже», ни «дешевле» само по себе не хорошо и не плохо — это
                  вопрос к допущениям прогноза, поэтому тон нейтральный. */}
              <div className="sum-metric__val">
                {dev === null ? "—" : (dev >= 0 ? "+" : "−") + share(String(Math.abs(dev)))}
              </div>
              <div className="sum-metric__note">
                {dev === null
                  ? "доли нет — ориентир равен нулю"
                  : dev >= 0
                    ? "оценка дела выше ориентира"
                    : "оценка дела ниже ориентира"}
              </div>
            </div>
          </div>

          {view.caveats.map((c, i) => (
            <div className="field-note field-note--warn" key={i}>{c}</div>
          ))}
        </>
      ) : (
        <div className="val-blocked">
          <div className="val-blocked__title">Сравнение не посчитано</div>
          <ul className="proc-limits__list">
            {view.blockers.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        </div>
      )}

      <div className="page-sub" style={{ marginTop: 12 }}>Чего здесь нет</div>
      <ul className="sum-gaps">
        {view.not_computed.map((line, i) => <li key={i}>{line}</li>)}
      </ul>
    </div>
  );
}
