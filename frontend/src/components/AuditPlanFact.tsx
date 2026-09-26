import {
  ASSET_LINES,
  EQLIAB_LINES,
  INCOME_LINES,
  type AuditPlanFact as Result,
  type RealizedFlag,
} from "../api/audit";
import { fmtMoney } from "../format";

/**
 * План-факт после сделки (макет «Экран 17»; методика — SPEC, Приложение Т).
 *
 * Четыре решения методики видны на экране.
 *
 * **План вводится, факт уже есть.** Поля плана стоят рядом с фактом из отчётности —
 * второго источника фактических чисел экран не заводит.
 *
 * **Нулевой факт двусмыслен, и это сказано.** Ноль значит либо «выручки не было», либо
 * «период ещё не отражён»; платформа их не различает и молча не выбирает.
 *
 * **Отклонение оценивается с учётом направления**: себестоимость ниже плана красится
 * как успех, а не как недобор.
 *
 * **Предсказанное посчитано, фактическое введено** — обе половины сопоставления флагов
 * подписаны, чтобы «дисконт окупился» не читалось как один расчёт.
 */

const VERDICT: Record<Result["rows"][number]["verdict"], string> = {
  better: "pf--better",
  worse: "pf--worse",
  on_plan: "pf--on-plan",
};

const VERDICT_LABEL: Record<Result["rows"][number]["verdict"], string> = {
  better: "лучше плана",
  worse: "хуже плана",
  on_plan: "в пределах порога",
};

/** Строки, доступные для ввода плана: те же коды, что у факта. */
const PLAN_LINES: [string, string][] = [...INCOME_LINES, ...ASSET_LINES, ...EQLIAB_LINES];

const pct = (v: string | null): string =>
  v === null ? "—" : `${(Number(v) * 100).toLocaleString("ru-RU",
    { maximumFractionDigits: 1 })}%`;

const signed = (v: string): string => (Number(v) > 0 ? "+" : "") + fmtMoney(v);

export function AuditPlanFact({
  result,
  periods,
  plan,
  marks,
  onPlan,
  onMarks,
}: {
  result: Result;
  periods: string[];
  plan: Record<string, string[]>;
  marks: RealizedFlag[];
  onPlan: (next: Record<string, string[]>) => void;
  onMarks: (next: RealizedFlag[]) => void;
}) {
  const n = periods.length;

  const setPlan = (code: string, t: number, value: string) => {
    const row = [...(plan[code] ?? [])];
    while (row.length < n) row.push("");
    row[t] = value;
    onPlan({ ...plan, [code]: row });
  };

  const mark = (code: string): RealizedFlag =>
    marks.find((m) => m.code === code)
    ?? { code, realized: false, actual_cost: null, note: "" };
  const setMark = (code: string, patch: Partial<RealizedFlag>) => {
    const at = marks.findIndex((m) => m.code === code);
    if (at < 0) return onMarks([...marks, { ...mark(code), ...patch }]);
    onMarks(marks.map((m, i) => (i === at ? { ...m, ...patch } : m)));
  };

  const priced = result.flags.filter((f) => f.predicted !== null);

  return (
    <div>
      {result.caveats.map((c, i) => (
        <div className="field-note field-note--warn" key={i}>{c}</div>
      ))}

      {result.available ? (
        <>
          <div className="audit-block">
            <div className="tab-head" style={{ marginBottom: 8 }}>
              <div className="audit-block__title" style={{ marginBottom: 0 }}>
                Развёрнутый план-факт
              </div>
              {/* Охват виден, а не угадывается: период без плана в сравнение не идёт. */}
              <span className="page-sub">
                сравниваются периоды: {result.periods.join(", ")}
              </span>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="audit-grid pf-table">
                <thead>
                  <tr>
                    <th className="audit-grid__rowhead">Показатель</th>
                    <th>План продавца</th><th>Факт</th><th>Δ</th><th>Δ, %</th>
                    <th>Оценка</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row) => (
                    <tr key={row.code} className={VERDICT[row.verdict]}>
                      <td className="audit-grid__rowhead">
                        {row.label}
                        {row.note && <span className="eq-kind">{row.note}</span>}
                      </td>
                      <td>{fmtMoney(row.plan)}</td>
                      <td>{fmtMoney(row.fact)}</td>
                      <td>{signed(row.delta)}</td>
                      <td>{pct(row.delta_share)}</td>
                      {/* Оценка учитывает направление: у расхода минус — успех. */}
                      <td className="pf-verdict">{VERDICT_LABEL[row.verdict]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="audit-block">
            <div className="audit-block__title">Что из наших флагов сработало</div>
            <div className="pf-totals">
              <div className="sum-metric">
                <div className="mini-label">Предсказано платформой</div>
                <div className="sum-metric__val">{fmtMoney(result.predicted_total)}</div>
                <div className="sum-metric__note">
                  сумма влияния флагов, отмеченных как сработавшие
                </div>
              </div>
              <div className="sum-metric">
                <div className="mini-label">Фактически обошлось</div>
                <div className="sum-metric__val">{fmtMoney(result.realized_total)}</div>
                {/* Обе половины подписаны: иначе «окупился» читается как один расчёт. */}
                <div className="sum-metric__note">
                  введено аналитиком — платформа причин не видит и «сработал» не выводит
                </div>
              </div>
            </div>
          </div>
        </>
      ) : null}

      <div className="audit-block">
        <div className="audit-block__title">Прогноз продавца</div>
        <div className="page-sub" style={{ marginBottom: 10 }}>
          Внесите план из инвестиционного меморандума по тем же периодам, что и
          отчётность. Факт вводить не нужно — это сама отчётность дела: второго
          источника фактических чисел план-факт не заводит.
        </div>
        {n === 0 ? (
          <div className="field-note">
            Периоды не заданы — вносить план не к чему.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="audit-grid">
              <thead>
                <tr>
                  <th className="audit-grid__rowhead">Статья</th>
                  {periods.map((p) => <th key={p}>{p}</th>)}
                </tr>
              </thead>
              <tbody>
                {PLAN_LINES.map(([code, label]) => (
                  <tr key={code}>
                    <td className="audit-grid__rowhead">{label}</td>
                    {periods.map((p, t) => (
                      <td key={p}>
                        <input
                          className="audit-cell"
                          inputMode="decimal"
                          aria-label={`${label}, ${p}: план`}
                          value={plan[code]?.[t] ?? ""}
                          onChange={(e) => setPlan(code, t, e.target.value)}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="audit-block">
        <div className="audit-block__title">Реализовавшиеся риски</div>
        <div className="page-sub" style={{ marginBottom: 10 }}>
          Сработал ли флаг, платформа не знает: она видит отчётность, а не причины.
          Отметьте сами и укажите, во что риск обошёлся. Предсказанная величина слева
          посчитана платформой — сравнение честно ровно в одну сторону.
        </div>

        {result.flags.length === 0 ? (
          <div className="field-note">
            Флагов в деле нет — сопоставлять нечего.
          </div>
        ) : (
          result.flags.map((f) => {
            const m = mark(f.code);
            return (
              <div className="pf-flag" key={f.code}>
                <label className="pf-flag__check">
                  <input type="checkbox" checked={m.realized}
                         aria-label={`${f.title}: сработал`}
                         onChange={(e) => setMark(f.code, { realized: e.target.checked })} />
                  <span className="pf-flag__title">{f.title}</span>
                </label>
                <div className="pf-flag__pred">
                  {/* Прочерк, а не ноль: у флага без меры сводить факт не с чем. */}
                  {f.predicted === null
                    ? <span className="eq-kind">денежной меры нет — не сопоставляется</span>
                    : <>предсказано {fmtMoney(f.predicted)}</>}
                </div>
                <input className="input" inputMode="decimal"
                       placeholder="фактически обошлось"
                       aria-label={`${f.title}: фактическая потеря`}
                       value={m.actual_cost ?? ""}
                       onChange={(e) => setMark(f.code, {
                         // Пустое поле — «факт ещё не оценён», а не «обошёлся в ноль».
                         actual_cost: e.target.value.trim() === "" ? null : e.target.value,
                       })} />
                <input className="input" placeholder="что произошло"
                       aria-label={`${f.title}: пояснение`}
                       value={m.note}
                       onChange={(e) => setMark(f.code, { note: e.target.value })} />
              </div>
            );
          })
        )}
        {priced.length < result.flags.length && (
          <div className="field-note">
            Часть флагов не имеет денежной меры — в сопоставление они не входят:
            предсказанной величины у них нет вовсе.
          </div>
        )}
      </div>

      <div className="audit-block">
        <div className="audit-block__title">Чего план-факт не считает</div>
        <ul className="sum-gaps">
          {result.not_computed.map((line, i) => <li key={i}>{line}</li>)}
        </ul>
      </div>
    </div>
  );
}
