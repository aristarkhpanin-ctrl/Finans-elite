import {
  ADJUSTMENT_KINDS,
  type AdjustmentKind,
  type AuditEarnings as Quality,
  type EarningsAdjustment,
} from "../api/audit";
import { IconTrash } from "./icons";
import { Button } from "./ui";
import { fmtMoney } from "../format";

/**
 * Качество прибыли и нормализация (макет «Экран 7»; методика — SPEC, Приложение К).
 *
 * Два решения методики видны прямо на экране.
 *
 * **Показатель назван своим именем.** Без введённой амортизации EBITDA не существует,
 * и нормализуется EBIT — экран пишет «EBIT», а не «EBITDA». Подписать одно другим
 * значило бы сдвинуть мультипликатор сделки на всю амортизацию.
 *
 * **Буква качества — объявленное соглашение, а не измерение.** Она сравнивает два
 * числа по записанной шкале, и рядом всегда стоит расхождение в процентах: читатель
 * должен видеть, из чего буква получилась.
 */

const GRADE_NOTE: Record<string, string> = {
  A: "grade--a",
  B: "grade--b",
  C: "grade--c",
};

const pct = (v: string | null): string =>
  v === null ? "—" : `${(Number(v) * 100).toLocaleString("ru-RU",
    { maximumFractionDigits: 1 })}%`;

export function AuditEarnings({
  quality,
  periods,
  adjustments,
  onChange,
  hasDepreciation,
}: {
  quality: Quality;
  periods: string[];
  adjustments: EarningsAdjustment[];
  onChange: (next: EarningsAdjustment[]) => void;
  /** Введена ли справочная строка амортизации — от неё зависит само имя показателя. */
  hasDepreciation: boolean;
}) {
  const n = periods.length;

  const upd = (i: number, patch: Partial<EarningsAdjustment>) =>
    onChange(adjustments.map((a, k) => (k === i ? { ...a, ...patch } : a)));
  const setAmount = (i: number, t: number, v: string) => {
    const row = [...(adjustments[i].amounts ?? [])];
    while (row.length < n) row.push("");
    row[t] = v;
    upd(i, { amounts: row });
  };

  return (
    <div>
      <div className="eq-head">
        <div>
          <div className="mini-label">Нормализуется</div>
          <div className="eq-base">{quality.base_code}</div>
          {!hasDepreciation && (
            // Не сноска, а суть: покупатель, умноживший мультипликатор на EBIT
            // вместо EBITDA, ошибётся ровно на амортизацию.
            <div className="eq-hint">
              Амортизация не введена, поэтому EBITDA не считается — нормализуется EBIT.
              Заполните справочную строку «в т.ч. амортизация» на вводе отчётности,
              чтобы получить EBITDA.
            </div>
          )}
        </div>
        {quality.grade && (
          <div className={"eq-grade " + (GRADE_NOTE[quality.grade] ?? "")}>
            <div className="eq-grade__letter">{quality.grade}</div>
            <div className="eq-grade__body">
              <div className="eq-grade__note">{quality.grade_note}</div>
              <div className="eq-grade__dev">
                Расхождение с отчётным: {pct(quality.deviation)} · шкала: A до 5%,
                B до 20%, C свыше — соглашение методики, а не измерение.
              </div>
            </div>
          </div>
        )}
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="audit-grid eq-table">
          <thead>
            <tr>
              <th className="audit-grid__rowhead">Показатель</th>
              {periods.map((p) => <th key={p}>{p}</th>)}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="audit-grid__rowhead">{quality.base_code} по отчётности</td>
              {quality.reported.map((v, t) => <td key={t}>{fmtMoney(v)}</td>)}
            </tr>
            {quality.adjustments.map((a, i) => (
              <tr key={i} className="eq-row--adj">
                <td className="audit-grid__rowhead" title={a.kind_label}>
                  {a.label}
                  <span className="eq-kind">{a.kind_label}</span>
                </td>
                {a.amounts.map((v, t) => <td key={t}>{fmtMoney(v)}</td>)}
              </tr>
            ))}
            <tr className="eq-row--total">
              <td className="audit-grid__rowhead">
                {quality.base_code} нормализованный
              </td>
              {quality.normalized.map((v, t) => <td key={t}>{fmtMoney(v)}</td>)}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="audit-block">
        <div className="tab-head" style={{ marginBottom: 10 }}>
          <div className="audit-block__title" style={{ marginBottom: 0 }}>Корректировки</div>
          <Button variant="ghost"
                  onClick={() => onChange([...adjustments,
                                           { label: "", kind: "one_off", amounts: [] }])}>
            ＋&nbsp;&nbsp;Корректировка
          </Button>
        </div>

        <div className="page-sub" style={{ marginBottom: 10 }}>
          Нормализация — суждение, а не расчёт: что считать разовым доходом и какое
          вознаграждение собственника избыточно, знаете вы, а не формула. «+» возвращает
          прибыль (убрали лишний расход), «−» убирает (разовый доход не повторится).
        </div>

        {adjustments.length === 0 ? (
          <div className="field-note">
            Корректировок нет — нормализованный показатель равен отчётному. Это тоже
            ответ: отчётность принята как есть.
          </div>
        ) : (
          adjustments.map((a, i) => (
            <div className="eq-editor" key={i}>
              <input
                className="input"
                placeholder="Причина корректировки (обязательно)"
                aria-label="Причина корректировки"
                value={a.label}
                onChange={(e) => upd(i, { label: e.target.value })}
              />
              <select
                className="select"
                aria-label="Вид корректировки"
                value={a.kind}
                onChange={(e) => upd(i, { kind: e.target.value as AdjustmentKind })}
              >
                {ADJUSTMENT_KINDS.map(([k, label]) => (
                  <option key={k} value={k}>{label}</option>
                ))}
              </select>
              <div className="eq-amounts">
                {periods.map((p, t) => (
                  <input
                    key={p}
                    className="input"
                    inputMode="decimal"
                    placeholder={p}
                    aria-label={`${p}: сумма корректировки`}
                    value={a.amounts?.[t] ?? ""}
                    onChange={(e) => setAmount(i, t, e.target.value)}
                  />
                ))}
              </div>
              <button type="button" className="icon-action icon-action--danger"
                      title="Удалить корректировку"
                      onClick={() => onChange(adjustments.filter((_, k) => k !== i))}>
                <IconTrash size={15} />
              </button>
              {!a.label.trim() && (
                // Поправка без причины не применяется — и об этом сказано здесь,
                // а не выяснится по неизменившемуся итогу.
                <div className="field-note field-note--warn eq-editor__note">
                  Без причины корректировка не применяется: нормализованный показатель,
                  который нельзя объяснить, нельзя и защитить в переговорах.
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
