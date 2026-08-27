import type { AuditHeadMetric, AuditSummary as Summary } from "../api/audit";
import { Button } from "./ui";
import { fmtMoney } from "../format";

/**
 * Сводка дела и вердикт (макет «Экран 1»; методика — SPEC, Приложение Н).
 *
 * Экран собирает готовое и **ничего не считает заново**. Три решения видны на нём
 * прямо.
 *
 * **Вердикт идёт вместе с охватом.** «Критических отклонений не выявлено» при охвате
 * 60% — это оценка шести десятых работы, и обе цифры стоят рядом, а не через экран
 * друг от друга.
 *
 * **Оценки сделки здесь нет.** Макет показывает «Дисконт к цене 18%» и «Справедливо
 * 1 020 млн ₽ вместо запрошенных 1 240 млн ₽» — ни одной из этих величин у платформы
 * не существует: запрошенной цены в модели нет, DCF не построен, бенчмарков нет.
 * Число, выведенное из ничего, унесли бы в переговоры. На его месте — оценённое
 * влияние флагов, и сказано, что скидкой оно не является.
 *
 * **Пробелы перечислены.** Отсутствующий раздел читается как благополучие, поэтому
 * сводка называет то, чего не считает, сама.
 */

const VERDICT: Record<Summary["verdict"], string> = {
  unreliable: "verdict--unreliable",
  risk: "verdict--risk",
  warning: "verdict--warning",
  ok: "verdict--ok",
};

const pct = (v: string | null): string =>
  v === null ? "—" : `${Math.round(Number(v) * 100)}%`;

/** Кратность: «2,4×». Не деньги и не процент — своя подпись. */
const ratio = (v: string): string =>
  `${Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 2 })}×`;

function metricValue(m: AuditHeadMetric): string {
  if (m.unit === "grade") return m.text || "—";
  // Прочерк, а не ноль: «не считается» и «равно нулю» — разные факты.
  if (m.value === null) return "—";
  return m.unit === "ratio" ? ratio(m.value) : fmtMoney(m.value);
}

export function AuditSummary({
  summary,
  onInput,
  onFlags,
  onProcedures,
  onOpinion,
}: {
  summary: Summary;
  onInput: () => void;
  onFlags: () => void;
  onProcedures: () => void;
  onOpinion: () => void;
}) {
  if (summary.state === "empty") {
    return (
      <div className="tab-empty">
        <div className="tab-empty__title">{summary.headline}</div>
        <div className="tab-empty__sub">{summary.detail}</div>
        <div style={{ marginTop: 16 }}>
          <Button onClick={onInput}>Перейти к вводу отчётности</Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className={"verdict " + VERDICT[summary.verdict]}>
        <div className="verdict__main">
          <div className="mini-label">Вердикт</div>
          <div className="verdict__headline">{summary.headline}</div>
          <div className="verdict__detail">{summary.detail}</div>
        </div>
        {/* Охват стоит внутри карточки вердикта, а не отдельным блоком: это его
            ограничение, а не соседняя метрика. */}
        <div className="verdict__coverage">
          <div className="mini-label">Охват проверки</div>
          <div className="verdict__coverage-val">{pct(summary.coverage)}</div>
          {summary.coverage !== null && (
            <button type="button" className="linkish" onClick={onProcedures}>
              {summary.open_procedures} незакрытых процедур
            </button>
          )}
        </div>
      </div>

      <div className="sum-metrics">
        {summary.metrics.map((m) => (
          <div className={"sum-metric tone--" + m.tone} key={m.key}>
            <div className="mini-label">{m.label}</div>
            <div className="sum-metric__val">{metricValue(m)}</div>
            {m.note && <div className="sum-metric__note">{m.note}</div>}
          </div>
        ))}
      </div>

      <div className="sum-row">
        <div className="audit-block sum-row__card">
          <div className="audit-block__title">Красные флаги</div>
          <div className="sum-flags">
            <span className="sum-flags__n sum-flags__n--risk">{summary.risk_flags}</span>
            <span>тяжёлых</span>
            <span className="sum-flags__n">{summary.warning_flags}</span>
            <span>внимания</span>
          </div>
          <div className="page-sub" style={{ marginTop: 10 }}>
            Оценённое влияние:{" "}
            <b>{summary.unpriced > 0 && Number(summary.priced_total) === 0
              ? "не определено"
              : fmtMoney(summary.priced_total)}</b>
            {summary.unpriced > 0 && <> · без денежной меры: {summary.unpriced}</>}
          </div>
          {/* Ровно на месте, где макет показывает «Дисконт к цене 18%». */}
          <div className="field-note field-note--warn" style={{ marginTop: 10 }}>
            Это <b>не скидка к цене</b>. Дисконт считается от запрошенной цены и оценки
            бизнеса — ни того, ни другого в деле пока нет.
          </div>
          <div style={{ marginTop: 12 }}>
            <Button variant="ghost" onClick={onFlags}>Открыть реестр флагов</Button>
          </div>
        </div>

        <div className="audit-block sum-row__card">
          <div className="audit-block__title">Что не посчитано</div>
          <div className="page-sub" style={{ marginBottom: 8 }}>
            Раздела, которого нет, читатель не замечает — и принимает его отсутствие
            за благополучие. Поэтому пробелы названы:
          </div>
          <ul className="sum-gaps">
            {summary.not_computed.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
          <div style={{ marginTop: 12 }}>
            <Button variant="ghost" onClick={onOpinion}>Открыть заключение</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
