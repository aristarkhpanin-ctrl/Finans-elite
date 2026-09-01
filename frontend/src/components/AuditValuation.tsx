import type { AuditValuation as Result, ValuationAssumptions } from "../api/audit";
import { emptyValuation } from "../api/audit";
import { Button } from "./ui";
import { fmtMoney, fracToPct, pctToFrac } from "../format";
import { useEffect, useState } from "react";

/**
 * Оценка стоимости и мост EV → цена (макет «Экран 4»; методика — SPEC, Прил. П).
 *
 * Четыре решения методики видны на экране.
 *
 * **Прогноз вводится, а не выводится.** В деле есть только прошлое; экстраполировать
 * выручку «как росла, так и будет» значило бы выдать регрессию за прогноз. Связь с
 * проверкой одна: база прогноза — **нормализованный** показатель.
 *
 * **Не посчитано ≠ ноль.** Не хватает входных данных — экран говорит, чего именно, и
 * не показывает ни стоимости, ни моста: «бизнес стоит 0» и «оценка не посчитана» —
 * разные утверждения.
 *
 * **Забалансовое из моста исключено** (Л.1) и названо отдельной оговоркой: условное
 * обязательство ещё не наступило, но покупатель обязан учесть его сам.
 *
 * **Дисконта нет без цены продавца.** Величина без второго операнда — не ноль
 * процентов, её просто нет.
 */

const pct = (v: string | null, digits = 1): string =>
  v === null ? "—" : `${(Number(v) * 100).toLocaleString("ru-RU",
    { maximumFractionDigits: digits })}%`;

const mult = (v: string | null): string =>
  v === null ? "—" : `${Number(v).toLocaleString("ru-RU",
    { maximumFractionDigits: 2 })}×`;

const factor = (v: string): string =>
  Number(v).toLocaleString("ru-RU", { minimumFractionDigits: 3,
                                      maximumFractionDigits: 3 });

/** Коэффициент дисконтирования терминальной стоимости; при нулевой — прочерк. */
const terminalFactor = (r: Result): string => {
  const tv = Number(r.terminal_value);
  return tv ? factor(String(Number(r.pv_terminal) / tv)) : "—";
};

/**
 * Процентное поле над долей в модели. Черновик набирается локально: поле, выведенное
 * из модели пересчётом, стирало бы набираемую запятую, и десятичную ставку было бы
 * не ввести.
 */
function PctInput({ value, onChange, label }: {
  value: string; onChange: (frac: string) => void; label: string;
}) {
  const [draft, setDraft] = useState(() => fracToPct(value));
  useEffect(() => {
    if (pctToFrac(draft) !== value && !(draft === "" && value === "")) {
      setDraft(fracToPct(value));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <input className="input" inputMode="decimal" aria-label={label} value={draft}
           onChange={(e) => {
             setDraft(e.target.value);
             const frac = pctToFrac(e.target.value);
             if (frac !== "" || e.target.value.trim() === "") onChange(frac || "0");
           }} />
  );
}

/** Ряд допущений по годам: пустая ячейка продлевается последним значением (П.1). */
function YearRow({ label, hint, values, horizon, onChange, percent = false }: {
  label: string; hint: string; values: string[]; horizon: number;
  onChange: (next: string[]) => void; percent?: boolean;
}) {
  const set = (i: number, v: string) => {
    const row = [...values];
    while (row.length <= i) row.push("");
    row[i] = v;
    onChange(row);
  };
  return (
    <div className="val-row">
      <div className="val-row__head">
        <span className="mini-label">{label}</span>
        <span className="val-row__hint">{hint}</span>
      </div>
      <div className="val-row__cells">
        {Array.from({ length: horizon }, (_, i) => (
          percent ? (
            <PctInput key={i} label={`${label}, год ${i + 1}`}
                      value={values[i] ?? ""}
                      onChange={(frac) => set(i, frac)} />
          ) : (
            <input key={i} className="input" inputMode="decimal"
                   aria-label={`${label}, год ${i + 1}`}
                   value={values[i] ?? ""}
                   onChange={(e) => set(i, e.target.value)} />
          )
        ))}
      </div>
    </div>
  );
}

export function AuditValuation({
  result,
  assumptions,
  onChange,
}: {
  result: Result;
  assumptions: ValuationAssumptions | undefined;
  onChange: (next: ValuationAssumptions) => void;
}) {
  const a = assumptions ?? emptyValuation();
  const upd = (patch: Partial<ValuationAssumptions>) => onChange({ ...a, ...patch });
  const horizon = a.horizon_years || 5;

  return (
    <div>
      <div className="tab-head" style={{ marginBottom: 14 }}>
        <label className="obl-cell--check">
          <input type="checkbox" checked={a.enabled}
                 onChange={(e) => upd({ enabled: e.target.checked })} />
          <span>Считать оценку</span>
        </label>
      </div>

      {result.blockers.length > 0 ? (
        // Ни стоимости, ни моста: «бизнес стоит 0» и «оценка не посчитана» — разное.
        <div className="val-blocked">
          <div className="val-blocked__title">Оценка не посчитана</div>
          <ul className="proc-limits__list">
            {result.blockers.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        </div>
      ) : (
        <>
          <div className="val-head">
            <div>
              <div className="mini-label">Цена за 100% доли</div>
              <div className="val-head__val">{fmtMoney(result.equity_value ?? "0")}</div>
              {result.equity_min !== null && (
                <div className="val-head__range">
                  Диапазон по чувствительности: {fmtMoney(result.equity_min)} —{" "}
                  {fmtMoney(result.equity_max ?? "0")}
                </div>
              )}
            </div>
            {result.asking_price !== null ? (
              <div className="val-head__ask">
                <div className="mini-label">Запрошено продавцом</div>
                <div className="val-head__askval">{fmtMoney(result.asking_price)}</div>
                <div className={"val-head__disc "
                                + (Number(result.discount) >= 0 ? "tone--ok" : "tone--risk")}>
                  {Number(result.discount) >= 0
                    ? <>Дисконт к цене {pct(result.discount, 0)}</>
                    : <>Наша оценка выше запрошенной на {pct(String(-Number(result.discount)), 0)}</>}
                </div>
              </div>
            ) : (
              <div className="val-head__ask">
                <div className="field-note field-note--warn" style={{ margin: 0 }}>
                  Цена продавца не введена — дисконта не существует. Это не ноль
                  процентов: без второго операнда величины просто нет.
                </div>
              </div>
            )}
          </div>

          <div className="sum-metrics">
            <div className="sum-metric">
              <div className="mini-label">Enterprise Value</div>
              <div className="sum-metric__val">
                {fmtMoney(result.enterprise_value ?? "0")}
              </div>
              <div className="sum-metric__note">
                терминальная стоимость — {pct(result.terminal_share, 0)} итога
              </div>
            </div>
            <div className="sum-metric">
              <div className="mini-label">EV / {result.base_code}</div>
              <div className="sum-metric__val">{mult(result.implied_multiple)}</div>
              {/* Не рыночный ориентир: базы сделок-аналогов у платформы нет. */}
              <div className="sum-metric__note">
                наш подразумеваемый мультипликатор, не рыночный ориентир
              </div>
            </div>
            <div className="sum-metric">
              <div className="mini-label">База прогноза ({result.base_code} → EBIT)</div>
              <div className="sum-metric__val">{fmtMoney(result.base_ebit)}</div>
              <div className="sum-metric__note">
                нормализованный EBIT последнего периода — ради этого нормализация и
                делалась
              </div>
            </div>
          </div>

          {result.warnings.map((w, i) => (
            <div className="field-note field-note--warn" key={i}>{w}</div>
          ))}

          <div className="sum-row" style={{ marginTop: 14 }}>
            <div className="audit-block sum-row__card">
              <div className="audit-block__title">Мост EV → цена</div>
              <div className="val-bridge">
                {result.bridge.map((b, i) => (
                  <div className={"val-bridge__row"
                                  + (b.kind === "total" ? " val-bridge__row--total" : "")}
                       key={i}>
                    <span className="val-bridge__label">
                      {b.kind === "subtract" ? "− " : b.kind === "add" && i > 0 ? "+ " : ""}
                      {b.label}
                      {b.note && <span className="eq-kind">{b.note}</span>}
                    </span>
                    <span className="val-bridge__val">{fmtMoney(b.amount)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="audit-block sum-row__card">
              <div className="audit-block__title">Что не посчитано</div>
              <ul className="sum-gaps">
                {result.not_computed.map((line, i) => <li key={i}>{line}</li>)}
              </ul>
            </div>
          </div>

          <div className="audit-block">
            <div className="audit-block__title">Дисконтированный поток</div>
            <div className="page-sub" style={{ marginBottom: 10 }}>
              FCFF = EBIT × (1 − ставка налога) + Амортизация − Капвложения −
              ΔОборотный капитал. Амортизация растёт вместе с показателем.
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="audit-grid">
                <thead>
                  <tr>
                    <th className="audit-grid__rowhead">Год</th>
                    <th>EBIT</th><th>Аморт.</th><th>Капвл.</th><th>ΔОК</th>
                    <th>FCFF</th><th>Коэф.</th><th>PV</th>
                  </tr>
                </thead>
                <tbody>
                  {result.years.map((y) => (
                    <tr key={y.year}>
                      <td className="audit-grid__rowhead">{y.year}</td>
                      <td>{fmtMoney(y.ebit)}</td>
                      <td>{fmtMoney(y.depreciation)}</td>
                      <td>{fmtMoney(y.capex)}</td>
                      <td>{fmtMoney(y.nwc_change)}</td>
                      <td>{fmtMoney(y.fcff)}</td>
                      <td>{factor(y.discount_factor)}</td>
                      <td>{fmtMoney(y.present_value)}</td>
                    </tr>
                  ))}
                  <tr className="eq-row--total">
                    <td className="audit-grid__rowhead" colSpan={5}>
                      Терминальная стоимость (Гордон, рост {pct(result.terminal_growth)})
                    </td>
                    {/* Недисконтированная величина рядом с приведённой: доля
                        терминальной стоимости — главный вопрос к любому DCF, и
                        разрыв между ними её объясняет. */}
                    <td>{fmtMoney(result.terminal_value ?? "0")}</td>
                    <td>{terminalFactor(result)}</td>
                    <td>{fmtMoney(result.pv_terminal ?? "0")}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="audit-block">
            <div className="audit-block__title">Чувствительность · цена за 100%</div>
            <div className="page-sub" style={{ marginBottom: 10 }}>
              По вертикали ставка дисконтирования, по горизонтали рост в постпрогнозе.
              Диапазон выше — минимум и максимум этой сетки: отдельных сценариев нет,
              они отвечали бы на тот же вопрос. Пустая клетка — рост не ниже ставки:
              стоимости там не существует, и ноль читался бы как «ничего не стоит».
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="audit-grid val-sens">
                <thead>
                  <tr>
                    <th className="audit-grid__rowhead">WACC \ рост</th>
                    {result.sensitivity_growth.map((g, i) => (
                      <th key={i}>{pct(g)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.sensitivity.map((row, i) => (
                    <tr key={i}>
                      <td className="audit-grid__rowhead">
                        {pct(result.sensitivity_wacc[i])}
                      </td>
                      {row.map((cell, j) => (
                        <td key={j}
                            className={i === 2 && j === 2 ? "val-sens__here" : undefined}>
                          {cell === null ? "—" : fmtMoney(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      <div className="audit-block">
        <div className="audit-block__title">Допущения прогноза</div>
        <div className="page-sub" style={{ marginBottom: 12 }}>
          В деле есть только прошлое. Экстраполировать выручку «как росла, так и будет»
          значило бы выдать регрессию за прогноз, поэтому рост, капвложения и изменение
          оборотного капитала задаёте вы. Ряд короче горизонта продлевается последним
          значением — обнулить хвост значило бы подставить наше допущение вместо
          вашего.
        </div>

        <div className="val-params">
          <label className="obl-cell">
            <span className="mini-label">Горизонт, лет</span>
            <input className="input" inputMode="numeric" aria-label="Горизонт прогноза"
                   value={String(a.horizon_years)}
                   onChange={(e) => upd({ horizon_years: Number(e.target.value) || 1 })} />
          </label>
          <label className="obl-cell">
            <span className="mini-label">Ставка дисконтирования, %</span>
            <PctInput value={a.wacc} label="Ставка дисконтирования"
                      onChange={(v) => upd({ wacc: v })} />
          </label>
          <label className="obl-cell">
            <span className="mini-label">Рост в постпрогнозе, %</span>
            <PctInput value={a.terminal_growth} label="Рост в постпрогнозе"
                      onChange={(v) => upd({ terminal_growth: v })} />
          </label>
          <label className="obl-cell">
            <span className="mini-label">Ставка налога, %</span>
            <PctInput value={a.tax_rate} label="Ставка налога"
                      onChange={(v) => upd({ tax_rate: v })} />
          </label>
          <label className="obl-cell">
            <span className="mini-label">Доля миноритариев</span>
            <input className="input" inputMode="decimal"
                   aria-label="Доля миноритариев" value={a.minority_interest}
                   onChange={(e) => upd({ minority_interest: e.target.value })} />
          </label>
          <label className="obl-cell">
            <span className="mini-label">Цена продавца</span>
            <input className="input" inputMode="decimal" placeholder="не введена"
                   aria-label="Запрошенная цена"
                   value={a.asking_price ?? ""}
                   onChange={(e) => upd({
                     // Пустое поле — «не введена», а не ноль: дисконта тогда не
                     // существует, и это другой факт, чем «дисконт 0%».
                     asking_price: e.target.value.trim() === "" ? null : e.target.value,
                   })} />
          </label>
        </div>

        <YearRow label="Рост показателя" hint="% к предыдущему году" percent
                 values={a.growth} horizon={horizon}
                 onChange={(next) => upd({ growth: next })} />
        <YearRow label="Капвложения" hint="в отчётной форме их нет — вводятся"
                 values={a.capex} horizon={horizon}
                 onChange={(next) => upd({ capex: next })} />
        <YearRow label="Δ оборотного капитала"
                 hint="из баланса не выводится: P_SHORT смешивает долг и кредиторку"
                 values={a.nwc_change} horizon={horizon}
                 onChange={(next) => upd({ nwc_change: next })} />

        {!a.enabled && (
          <div style={{ marginTop: 12 }}>
            <Button onClick={() => upd({ enabled: true })}>Включить оценку</Button>
          </div>
        )}
      </div>
    </div>
  );
}
