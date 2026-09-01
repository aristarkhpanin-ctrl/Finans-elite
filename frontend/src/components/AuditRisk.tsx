import {
  DISTRIBUTION_KINDS,
  RISK_PARAMS,
  type AuditRisk as Result,
  type AuditTornadoBar,
  type RiskAnalysis,
  type RiskDistribution,
  type RiskParam,
  emptyRisk,
  emptyUncertain,
} from "../api/audit";
import { IconTrash } from "./icons";
import { Button } from "./ui";
import { fmtMoney, fracToPct, pctToFrac } from "../format";
import { useEffect, useState } from "react";

/**
 * Анализ рисков оценки (макет «Экран 13»; методика — SPEC, Приложение Р).
 *
 * Три решения методики видны на экране.
 *
 * **Шаг торнадо показан рядом со столбцами.** Порядок столбцов — следствие соглашения
 * о шаге, а не измеренная влиятельность: торнадо, скрывающий свой шаг, выдаёт
 * соглашение за измерение. Поэтому шаг и виден, и настраивается.
 *
 * **Прогон без оценки назван, а не спрятан.** Ноль занизил бы медиану, а тихое
 * выбрасывание скрыло бы, что в части сценариев бизнес не оценивается вовсе.
 *
 * **Точность результата не выше точности догадки.** Медиана с перцентилями выглядит
 * измерением, но распределения придумал человек — это написано рядом с числами, а не
 * в сноске.
 */

const pct = (v: string | null, digits = 0): string =>
  v === null ? "—" : `${(Number(v) * 100).toLocaleString("ru-RU",
    { maximumFractionDigits: digits })}%`;

const signed = (v: string | null): string =>
  v === null ? "—" : (Number(v) > 0 ? "+" : "") + fmtMoney(v);

/** Процентное поле над долей в модели (черновик локальный — иначе запятая теряется). */
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

/** Поля распределения зависят от его вида: у равномерного нет моды, у нормального — границ. */
const FIELDS: Record<RiskDistribution["kind"], [keyof RiskDistribution, string][]> = {
  uniform: [["low", "от"], ["high", "до"]],
  normal: [["mean", "среднее"], ["std", "σ"]],
  triangular: [["low", "от"], ["mode", "мода"], ["high", "до"]],
};

function Tornado({ bars, base }: { bars: AuditTornadoBar[]; base: string | null }) {
  const scale = bars.reduce((m, b) => Math.max(
    m, Math.abs(Number(b.low_delta ?? 0)), Math.abs(Number(b.high_delta ?? 0))), 0);
  const width = (v: string | null) =>
    scale > 0 && v !== null ? `${(Math.abs(Number(v)) / scale) * 50}%` : "0%";

  return (
    <div className="torn">
      {bars.map((b) => (
        <div className="torn__row" key={b.param}>
          <div className="torn__label">
            <span className="torn__name">{b.label}</span>
            {/* Шаг у каждого столбца: без него порядок читается как измерение. */}
            <span className="torn__step">±{pct(b.step)}</span>
          </div>
          <div className="torn__track">
            <div className="torn__axis" />
            {(["low", "high"] as const).map((side) => {
              const delta = side === "low" ? b.low_delta : b.high_delta;
              if (delta === null) return null;
              const negative = Number(delta) < 0;
              return (
                <div
                  key={side}
                  className={"torn__fill " + (negative ? "torn__fill--neg" : "torn__fill--pos")}
                  style={negative
                    ? { right: "50%", width: width(delta) }
                    : { left: "50%", width: width(delta) }}
                />
              );
            })}
          </div>
          {/* Число красится по **знаку**, а не по стороне смещения: у ставки
              дисконтирования снижение поднимает цену, и «+162» в красном читалось бы
              как потеря. Рядом сказано, какое смещение дало этот эффект. */}
          <div className="torn__nums">
            {(["low", "high"] as const).map((side) => {
              const delta = side === "low" ? b.low_delta : b.high_delta;
              const sign = side === "low" ? "−" : "+";
              return (
                <span className="torn__num" key={side}>
                  <span className="torn__at">{sign}{pct(b.step)}</span>
                  <span className={Number(delta) < 0 ? "torn__neg" : "torn__pos"}>
                    {signed(delta)}
                  </span>
                </span>
              );
            })}
          </div>
          {b.note && <div className="torn__note">{b.note}</div>}
        </div>
      ))}
      <div className="torn__foot">
        Каждое допущение смещается отдельно, остальные держатся на базовом уровне;
        взаимодействия параметров торнадо не показывает. База — {fmtMoney(base ?? "0")}.
        <b> Порядок столбцов зависит от соглашения о шаге</b> — измените шаг ниже, чтобы
        проверить, устойчив ли он.
      </div>
    </div>
  );
}

export function AuditRisk({
  result,
  settings,
  onChange,
}: {
  result: Result;
  settings: RiskAnalysis | undefined;
  onChange: (next: RiskAnalysis) => void;
}) {
  const s = settings ?? emptyRisk();
  const upd = (patch: Partial<RiskAnalysis>) => onChange({ ...s, ...patch });
  const updUncertain = (i: number, patch: Partial<typeof s.uncertain[number]>) =>
    upd({ uncertain: s.uncertain.map((u, k) => (k === i ? { ...u, ...patch } : u)) });
  const mc = result.monte_carlo;
  const peak = mc ? mc.histogram.reduce((m, h) => Math.max(m, h.count), 0) : 0;

  return (
    <div>
      {!result.available ? (
        <div className="val-blocked">
          <div className="val-blocked__title">Анализировать нечего</div>
          <ul className="proc-limits__list">
            {result.blockers.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        </div>
      ) : (
        <>
          {result.warnings.map((w, i) => (
            <div className="field-note field-note--warn" key={i}>{w}</div>
          ))}

          <div className="audit-block">
            <div className="audit-block__title">Что двигает цену сильнее всего</div>
            <Tornado bars={result.tornado} base={result.base_price} />
          </div>

          <div className="audit-block">
            <div className="audit-block__title">Распределение справедливой цены</div>
            {mc === null ? (
              <div className="field-note">
                Неопределённых допущений не объявлено. Прогон по нулю распределений дал
                бы одну и ту же цену {s.iterations} раз и выглядел бы анализом — добавьте
                хотя бы одно распределение ниже.
              </div>
            ) : mc.valued === 0 ? (
              <div className="field-note field-note--warn">
                Ни один из {mc.iterations} прогонов не дал оценки: при заданных
                распределениях модель всюду выходит за пределы, где стоимость
                существует.
              </div>
            ) : (
              <>
                {/* Не сноска, а условие чтения всего блока. */}
                <div className="field-note field-note--warn" style={{ marginTop: 0 }}>
                  Числа ниже выглядят измерением, но они <b>ровно настолько хороши,
                  насколько верны заданные распределения</b>: их придумал человек, и
                  уверенность результата не может быть выше уверенности во входе.
                </div>

                <div className="mc-hist">
                  {mc.histogram.map((h, i) => (
                    <div className="mc-hist__col" key={i}
                         title={`${fmtMoney(h.from)} — ${fmtMoney(h.to)}: ${h.count}`}>
                      <div className="mc-hist__bar"
                           style={{ height: peak ? `${(h.count / peak) * 100}%` : "0%" }} />
                    </div>
                  ))}
                </div>
                <div className="mc-hist__axis">
                  <span>{fmtMoney(mc.minimum ?? "0")}</span>
                  <span>{fmtMoney(mc.maximum ?? "0")}</span>
                </div>

                <div className="sum-metrics" style={{ marginTop: 14 }}>
                  <div className="sum-metric">
                    <div className="mini-label">Медиана</div>
                    <div className="sum-metric__val">{fmtMoney(mc.median ?? "0")}</div>
                    <div className="sum-metric__note">
                      база — {fmtMoney(result.base_price ?? "0")}; расхождение{" "}
                      {pct(mc.median_drift, 1)}
                    </div>
                  </div>
                  <div className="sum-metric">
                    <div className="mini-label">P10 — P90</div>
                    <div className="sum-metric__val">
                      {fmtMoney(mc.p10 ?? "0")} — {fmtMoney(mc.p90 ?? "0")}
                    </div>
                    <div className="sum-metric__note">
                      восемь прогонов из десяти легли в этот интервал
                    </div>
                  </div>
                  <div className={"sum-metric"
                                  + (mc.below_asking !== null ? " tone--warn" : "")}>
                    <div className="mini-label">Ниже запрошенной цены</div>
                    <div className="sum-metric__val">
                      {mc.below_asking === null ? "—" : pct(mc.below_asking)}
                    </div>
                    <div className="sum-metric__note">
                      {mc.below_asking === null
                        ? "цена продавца не введена — вероятности не существует"
                        : `доля прогонов из ${mc.valued}`}
                    </div>
                  </div>
                  <div className={"sum-metric" + (mc.unvalued > 0 ? " tone--warn" : "")}>
                    <div className="mini-label">Прогонов без оценки</div>
                    <div className="sum-metric__val">{mc.unvalued}</div>
                    {/* Ноль занизил бы медиану, тихое выбрасывание скрыло бы факт. */}
                    <div className="sum-metric__note">
                      {mc.unvalued === 0
                        ? "во всех прогонах стоимость существует"
                        : "в них стоимости не существует; нулём они не заменены и из "
                          + "выборки не выброшены молча"}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="audit-block">
            <div className="audit-block__title">Что не посчитано</div>
            <ul className="sum-gaps">
              {result.not_computed.map((line, i) => <li key={i}>{line}</li>)}
            </ul>
          </div>
        </>
      )}

      <div className="audit-block">
        <div className="audit-block__title">Настройки анализа</div>
        <div className="val-params">
          <label className="obl-cell">
            <span className="mini-label">Шаг торнадо, %</span>
            <PctInput value={s.tornado_step} label="Шаг торнадо"
                      onChange={(v) => upd({ tornado_step: v })} />
          </label>
          <label className="obl-cell">
            <span className="mini-label">Прогонов Монте-Карло</span>
            <input className="input" inputMode="numeric" aria-label="Прогонов"
                   value={String(s.iterations)}
                   onChange={(e) => upd({ iterations: Number(e.target.value) || 100 })} />
          </label>
          <label className="obl-cell">
            <span className="mini-label">Зерно случайности</span>
            <input className="input" inputMode="numeric" aria-label="Зерно случайности"
                   value={String(s.seed)}
                   onChange={(e) => upd({ seed: Number(e.target.value) || 0 })} />
            {/* Не техническая деталь: без фиксированного зерна медиану нельзя назвать
                за столом переговоров — она менялась бы при каждом обновлении. */}
            <span className="val-row__hint">
              прогон воспроизводим: при том же зерне числа те же
            </span>
          </label>
        </div>

        <div className="tab-head" style={{ margin: "14px 0 8px" }}>
          <div className="audit-block__title" style={{ marginBottom: 0 }}>
            Неопределённые допущения
          </div>
          <Button variant="ghost"
                  onClick={() => upd({ uncertain: [...s.uncertain, emptyUncertain()] })}>
            ＋&nbsp;&nbsp;Допущение
          </Button>
        </div>

        <div className="page-sub" style={{ marginBottom: 10 }}>
          Распределение задаётся для <b>коэффициента</b>, а не для самого значения:
          выборка даёт множитель к базе, поэтому одно распределение годится и для
          ставки, и для суммы. «1.0» — база без изменения, «0.9» — на десятую меньше.
        </div>

        {s.uncertain.length === 0 ? (
          <div className="field-note">
            Неопределённых допущений нет — Монте-Карло не считается.
          </div>
        ) : (
          s.uncertain.map((u, i) => (
            <div className="risk-editor" key={i}>
              <select className="select" aria-label={`Допущение ${i + 1}: параметр`}
                      value={u.param}
                      onChange={(e) => updUncertain(i, { param: e.target.value as RiskParam })}>
                {RISK_PARAMS.map(([p, label]) => (
                  <option key={p} value={p}>{label}</option>
                ))}
              </select>
              <select className="select" aria-label={`Допущение ${i + 1}: распределение`}
                      value={u.distribution.kind}
                      onChange={(e) => updUncertain(i, {
                        distribution: { ...u.distribution,
                                        kind: e.target.value as RiskDistribution["kind"] },
                      })}>
                {DISTRIBUTION_KINDS.map(([k, label]) => (
                  <option key={k} value={k}>{label}</option>
                ))}
              </select>
              <div className="risk-editor__nums">
                {FIELDS[u.distribution.kind].map(([key, label]) => (
                  <input key={key} className="input" inputMode="decimal"
                         placeholder={label}
                         aria-label={`Допущение ${i + 1}: ${label}`}
                         value={(u.distribution[key] as string | null) ?? ""}
                         onChange={(e) => updUncertain(i, {
                           distribution: { ...u.distribution,
                                           [key]: e.target.value || null },
                         })} />
                ))}
              </div>
              <button type="button" className="icon-action icon-action--danger"
                      title={`Удалить допущение «${
                        RISK_PARAMS.find(([p]) => p === u.param)?.[1] ?? u.param}»`}
                      onClick={() => upd({
                        uncertain: s.uncertain.filter((_, k) => k !== i) })}>
                <IconTrash size={15} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
