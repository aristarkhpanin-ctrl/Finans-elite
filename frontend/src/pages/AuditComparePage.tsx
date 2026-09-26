import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  compareAuditSubjects,
  listAuditSubjects,
  type AuditComparison,
  type AuditCompareRow,
} from "../api/audit";
import { Button } from "../components/ui";
import { fmtMoney } from "../format";

/**
 * Сравнение дел (макет «Экран 20»; методика — SPEC, Приложение С).
 *
 * Три решения методики видны на экране.
 *
 * **«Кто лучше» — только там, где «лучше» определено.** У Enterprise Value и цены за
 * долю победителя нет по определению: больше — это размер сделки, а не её качество.
 * У строк без победителя стоит объяснение, а не пустая клетка.
 *
 * **Сводного балла с весами нет** — есть счёт побед по видимым построчно показателям:
 * балл прятал бы веса за собой.
 *
 * **Рекомендации по сделке нет.** Выбор зависит от стратегии покупателя и его
 * портфеля, а этого в деле нет; платформа, рекомендующая сделку, притворяется
 * инвестором. Экран говорит, что показало сравнение, и называет, чего он знать не может.
 */

const MAX_CASES = 4;

function cell(row: AuditCompareRow, i: number): string {
  if (row.unit === "text") return row.texts[i] || "—";
  const value = row.values[i];
  // Прочерк, а не ноль: «не считается» и «равно нулю» — разные факты.
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (row.unit === "percent") {
    return `${(n * 100).toLocaleString("ru-RU", { maximumFractionDigits: 0 })}%`;
  }
  if (row.unit === "ratio") {
    return `${n.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}×`;
  }
  if (row.unit === "count") return String(n);
  return fmtMoney(value);
}

function Comparison({ data }: { data: AuditComparison }) {
  return (
    <>
      <div className="cmp-wins">
        {data.cases.map((c, i) => (
          <div className="cmp-win" key={c.subject_id}>
            <div className="mini-label">{c.name}</div>
            <div className="cmp-win__val">
              {data.wins[i]} <span className="cmp-win__of">из {data.comparable}</span>
            </div>
            <div className="cmp-win__meta">
              {c.industry || "отрасль не указана"} · {c.currency} · {c.last_period}
            </div>
          </div>
        ))}
        {/* Не сноска: без этого счёт побед читается как балл, которого здесь нет. */}
        <div className="obl-totals__note">
          Счёт побед по <b>сопоставимым</b> показателям — все они видны построчно ниже.
          Сводного балла с весами здесь нет намеренно: балл прятал бы веса за собой, и
          два дела с разными весами получали бы разные баллы при тех же числах.
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="audit-grid cmp-table">
          <thead>
            <tr>
              <th className="audit-grid__rowhead">Показатель</th>
              {data.cases.map((c) => <th key={c.subject_id}>{c.name}</th>)}
              <th>Кто лучше</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.key}>
                <td className="audit-grid__rowhead">
                  {row.label}
                  {row.note && <span className="eq-kind">{row.note}</span>}
                </td>
                {data.cases.map((c, i) => (
                  <td key={c.subject_id}
                      className={row.winner === i ? "cmp-cell--win" : undefined}>
                    {cell(row, i)}
                  </td>
                ))}
                <td className="cmp-verdict">
                  {/* Прочерк здесь — не «ничья», а «сравнивать нечем»: причина в
                      пояснении к строке слева. */}
                  {row.winner === null ? "—" : data.cases[row.winner].name}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.caveats.length > 0 && (
        <div className="proc-limits">
          <div className="proc-limits__title">Что сравнимо, а что нет</div>
          <ul className="proc-limits__list">
            {data.caveats.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
      )}

      <div className="audit-block">
        <div className="audit-block__title">Чего это сравнение не говорит</div>
        <ul className="sum-gaps">
          {data.not_computed.map((line, i) => <li key={i}>{line}</li>)}
        </ul>
      </div>
    </>
  );
}

export function AuditComparePage() {
  const [selected, setSelected] = useState<string[]>([]);
  const subjects = useQuery({ queryKey: ["audit-subjects"], queryFn: listAuditSubjects });
  const compare = useMutation({ mutationFn: () => compareAuditSubjects(selected) });

  const toggle = (id: string) =>
    setSelected((prev) => prev.includes(id)
      ? prev.filter((x) => x !== id)
      : prev.length >= MAX_CASES ? prev : [...prev, id]);

  const list = subjects.data ?? [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Сравнение дел</h1>
          <div className="page-sub">
            До {MAX_CASES} дел рядом. Сравнение разовое: числа берутся по текущей
            отчётности дел, а не из сохранённого снимка.
          </div>
        </div>
        <Button disabled={selected.length < 2 || compare.isPending}
                onClick={() => compare.mutate()}>
          Сравнить{selected.length > 0 && ` (${selected.length})`}
        </Button>
      </div>

      <div className="audit-block">
        <div className="audit-block__title">Дела организации</div>
        {list.length === 0 ? (
          <div className="field-note">Дел пока нет — сравнивать нечего.</div>
        ) : (
          <div className="cmp-picker">
            {list.map((s) => {
              const on = selected.includes(s.id);
              const empty = s.n_periods === 0;
              return (
                <label className={"cmp-pick" + (on ? " cmp-pick--on" : "")} key={s.id}>
                  <input type="checkbox" checked={on} disabled={empty}
                         onChange={() => toggle(s.id)} />
                  <span className="cmp-pick__body">
                    <span className="cmp-pick__name">{s.name}</span>
                    <span className="cmp-pick__meta">
                      {/* Дело без отчётности выбрать нельзя, и сказано почему —
                          молча дизейблить значит оставить человека гадать. */}
                      {empty ? "отчётность не введена — сравнивать нечего"
                             : `${s.n_periods} периодов · ${s.industry || "отрасль не указана"}`}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        )}
        {selected.length >= MAX_CASES && (
          <div className="field-note">
            Больше {MAX_CASES} дел рядом не помещается — снимите одно, чтобы добавить другое.
          </div>
        )}
      </div>

      {compare.isError && (
        <div className="field-note field-note--warn">Не удалось сравнить дела.</div>
      )}
      {compare.data && <Comparison data={compare.data} />}
    </div>
  );
}
