import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { httpDetail } from "../../api/client";
import { BENCHMARK_METRICS, getBenchmarks, putBenchmarks,
         type BenchmarkIn } from "../../api/org";
import { IconTrash } from "../../components/icons";
import { useToast } from "../../components/Toast";
import { Button, Skeleton } from "../../components/ui";

/**
 * Справочник отраслевых ориентиров организации (SPEC, Прил. Ф).
 *
 * Макеты трижды обещают сравнение с отраслью, и трижды платформа отказывала: рыночной
 * статистики сделок у неё нет и взять её неоткуда. Ориентиры организации превращают
 * отказ в функцию — но только пока их не выдают за рынок, поэтому:
 *
 * * ориентир **подписан**: источник («медиана по трём сделкам фонда») — часть строки,
 *   а не примечание. Число без автора неотличимо от рыночной медианы;
 * * база названа явно (EV/EBITDA и EV/EBIT — разные величины), и сравнение пойдёт
 *   только по совпавшей базе;
 * * отрасль сопоставляется точным совпадением: угадывать, что «Перевозки» и
 *   «Грузоперевозки» — одно и то же, платформа не вправе, и это сказано на экране.
 *
 * Справочник правится как таблица и сохраняется целиком: что видно на экране, то и
 * записано. Частичные обновления развели бы экран и хранилище.
 */

/** Пустая строка: отрасль и значение вводятся, база — самая частая из трёх. */
const EMPTY: BenchmarkIn = { industry: "", metric: "ev_ebitda", value: "", source: "" };

const fmtDate = (iso: string): string =>
  new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit",
                                              year: "numeric" });

/** Строка готова к отправке: без отрасли и значения ориентира не существует. */
const filled = (r: BenchmarkIn): boolean =>
  r.industry.trim() !== "" && String(r.value).trim() !== "";

export function BenchmarksTab({ orgId, canManage }: { orgId: string; canManage: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data, isLoading } = useQuery({
    queryKey: ["benchmarks", orgId], queryFn: () => getBenchmarks(orgId),
  });

  /** Черновик таблицы: набираемое значение не должно стираться ответом сервера. */
  const [rows, setRows] = useState<BenchmarkIn[]>([]);
  const [updated, setUpdated] = useState<(string | null)[]>([]);
  useEffect(() => {
    if (!data) return;
    setRows(data.map((b) => ({ industry: b.industry, metric: b.metric,
                               value: String(b.value), source: b.source })));
    setUpdated(data.map((b) => b.updated_at));
  }, [data]);

  const save = useMutation({
    mutationFn: () => putBenchmarks(orgId, rows.filter(filled)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["benchmarks", orgId] });
      // Разбор дела сравнивает с ориентирами: правка справочника меняет его вывод.
      qc.invalidateQueries({ queryKey: ["audit-analysis"] });
      toast("Ориентиры сохранены", { kind: "success" });
    },
    // Отказ сервера содержательный (две строки на одну пару «отрасль + база»), его
    // текст и показываем: своя формулировка разошлась бы с правилом на бэкенде.
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось сохранить ориентиры",
                                   { kind: "error" }),
  });

  const upd = (i: number, patch: Partial<BenchmarkIn>) =>
    setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const drop = (i: number) => {
    setRows(rows.filter((_, j) => j !== i));
    setUpdated(updated.filter((_, j) => j !== i));
  };

  return (
    <div>
      <div className="terms-head" style={{ display: "flex", alignItems: "center",
                                           justifyContent: "space-between", marginTop: 0 }}>
        <span>Отраслевые ориентиры{data ? ` (${data.length})` : ""}</span>
        {canManage && (
          <Button onClick={() => { setRows([...rows, { ...EMPTY }]);
                                   setUpdated([...updated, null]); }}>
            ＋&nbsp;&nbsp;Добавить ориентир
          </Button>
        )}
      </div>

      <p className="page-sub" style={{ marginTop: 0, marginBottom: 14 }}>
        Платформа не собирает статистику сделок и не знает отраслевых медиан. Здесь
        живут <b>ваши</b> ориентиры: мультипликатор, который ваша организация считает
        типичным для отрасли. Дело сравнивается с ними на вкладке «Оценка» — и всегда
        с оговоркой, чьё это число.
      </p>

      {isLoading && (
        <div className="org-tbl">
          {[0, 1].map((i) => (
            <div className="org-row" key={i}><Skeleton width={280} height={22} /></div>
          ))}
        </div>
      )}

      {/* Пустой экран после удаления последней строки — ещё не пустой справочник:
          удаление не сохранено, и звать «заведите первый» рано. */}
      {!isLoading && rows.length === 0 && (data?.length ?? 0) === 0 && (
        <div className="tab-empty">
          <div className="tab-empty__title">Ориентиров пока нет</div>
          <div className="tab-empty__sub">
            {canManage
              ? "Заведите первый — например, «Перевозки · EV / EBITDA · 5,0 · медиана "
                + "по трём сделкам фонда». Пока справочник пуст, на вкладке «Оценка» "
                + "дела будет сказано, что сравнивать не с чем."
              : "Справочник ведут владелец и администратор организации."}
          </div>
        </div>
      )}

      {rows.length > 0 && (
        <div className="audit-block" style={{ overflowX: "auto" }}>
          <table className="audit-grid bm-tbl">
            <thead>
              <tr>
                <th className="audit-grid__rowhead">Отрасль</th>
                <th>База</th>
                <th>Ориентир, ×</th>
                <th>Источник</th>
                <th>Обновлён</th>
                {canManage && <th />}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="audit-grid__rowhead">
                    <input className="input" aria-label={`Отрасль, строка ${i + 1}`}
                           placeholder="как в карточке дела"
                           value={r.industry} disabled={!canManage}
                           onChange={(e) => upd(i, { industry: e.target.value })} />
                  </td>
                  <td>
                    <select className="input" aria-label={`База, строка ${i + 1}`}
                            value={r.metric} disabled={!canManage}
                            onChange={(e) => upd(i, {
                              metric: e.target.value as BenchmarkIn["metric"],
                            })}>
                      {BENCHMARK_METRICS.map(([key, label]) => (
                        <option key={key} value={key}>{label}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input className="input" inputMode="decimal"
                           aria-label={`Ориентир, строка ${i + 1}`}
                           value={String(r.value)} disabled={!canManage}
                           onChange={(e) => upd(i, { value: e.target.value })} />
                  </td>
                  <td>
                    <input className="input" aria-label={`Источник, строка ${i + 1}`}
                           placeholder="кто и по чему это посчитал"
                           value={r.source} disabled={!canManage}
                           onChange={(e) => upd(i, { source: e.target.value })} />
                  </td>
                  {/* Дата — серверная: она про то, когда ориентир записали, а не про
                      то, что сейчас в поле. */}
                  <td className="muted">{updated[i] ? fmtDate(updated[i]!) : "не сохранён"}</td>
                  {canManage && (
                    <td>
                      <button type="button" className="icon-action icon-action--danger"
                              title="Удалить ориентир" onClick={() => drop(i)}>
                        <IconTrash size={15} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Кнопка остаётся и когда на экране не осталось ни строки: иначе удалить
          последний ориентир было бы нельзя — строка исчезала бы с экрана и
          возвращалась из хранилища при следующем открытии. */}
      {canManage && (rows.length > 0 || (data?.length ?? 0) > 0) && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
          <Button loading={save.isPending} onClick={() => save.mutate()}>Сохранить</Button>
          <span className="muted">
            Строки без отрасли или значения не сохраняются: ориентира без числа не бывает.
          </span>
        </div>
      )}

      <div className="rbac-card">
        <div className="rbac-card__head">Как это читается в деле</div>
        <div className="rbac-grid">
          <div className="rbac-item">
            <span className="rbac-item__badge">Отрасль</span>
            <span className="rbac-item__desc">
              Совпадает точно (регистр и лишние пробелы не в счёт). «Перевозки» и
              «Грузоперевозки» — разные отрасли: угадывать платформа не вправе.
            </span>
          </div>
          <div className="rbac-item">
            <span className="rbac-item__badge">База</span>
            <span className="rbac-item__desc">
              Сравнение идёт только при совпадении базы. База дела — EBITDA, если в
              отчётности есть амортизация, иначе EBIT.
            </span>
          </div>
          <div className="rbac-item">
            <span className="rbac-item__badge">Источник</span>
            <span className="rbac-item__desc">
              Печатается рядом с числом на экране, в документе и в выгрузке: ориентир
              без автора неотличим от рыночной медианы, которой у платформы нет.
            </span>
          </div>
        </div>
      </div>

      {!canManage && (
        <p className="muted" style={{ marginTop: 12 }}>
          🔒 Справочник ориентиров правят владелец и администратор организации.
        </p>
      )}
    </div>
  );
}
