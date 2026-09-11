import {
  MARK_STATUSES,
  type AuditProcedure,
  type AuditProcedures as Report,
  type CustomProcedure,
  type MarkStatus,
  type ProcedureMark,
  type ProcedureStatus,
  emptyCustomProcedure,
} from "../api/audit";
import { IconTrash } from "./icons";
import { Button } from "./ui";

/**
 * Чек-лист процедур (макет «Экран 21»; методика — SPEC, Приложение М).
 *
 * Три решения методики видны прямо на экране.
 *
 * **Исполнитель назван у каждой процедуры.** Макет подписывает «базовая ·
 * автоматически» под сверкой с банковской выпиской и картотекой арбитражных дел.
 * Так подписать нельзя: платформа не выполняет того, чего не читает. Процедуре без
 * входных данных нужен человек — и это сказано, а не отложено «на потом».
 *
 * **Статус системной процедуры не редактируется.** Он выводится из фактического
 * прогона, и `no_data` — **не «пройдено»**: покрытие процентов при незаполненной
 * строке процентов не проверено, а не благополучно.
 *
 * **Границы проверки показаны рядом с охватом.** «Охват 70%» без перечня тех 30%
 * читается как «почти всё проверено», а не как «треть не проверялась».
 */

const STATUS: Record<ProcedureStatus, { label: string; cls: string }> = {
  pass: { label: "Проверено", cls: "proc--pass" },
  finding: { label: "Есть находка", cls: "proc--finding" },
  no_data: { label: "Нет данных", cls: "proc--nodata" },
  done: { label: "Выполнено", cls: "proc--pass" },
  skipped: { label: "Снято", cls: "proc--skipped" },
  pending: { label: "Не выполнено", cls: "proc--pending" },
};

const pct = (v: string | null): string =>
  v === null ? "—" : `${Math.round(Number(v) * 100)}%`;

export function AuditProcedures({
  report,
  marks,
  custom,
  onMarks,
  onCustom,
}: {
  report: Report;
  marks: ProcedureMark[];
  custom: CustomProcedure[];
  onMarks: (next: ProcedureMark[]) => void;
  onCustom: (next: CustomProcedure[]) => void;
}) {
  const setMark = (code: string, patch: Partial<ProcedureMark>) => {
    const at = marks.findIndex((m) => m.code === code);
    if (at < 0) {
      onMarks([...marks, { code, status: "pending", note: "", ...patch }]);
      return;
    }
    onMarks(marks.map((m, i) => (i === at ? { ...m, ...patch } : m)));
  };
  const mark = (code: string): ProcedureMark =>
    marks.find((m) => m.code === code) ?? { code, status: "pending", note: "" };

  const updCustom = (i: number, patch: Partial<CustomProcedure>) =>
    onCustom(custom.map((c, k) => (k === i ? { ...c, ...patch } : c)));

  // Группы в порядке каталога; свои процедуры редактируются отдельным блоком ниже.
  const groups: [string, AuditProcedure[]][] = [];
  for (const item of report.items) {
    if (item.code.startsWith("custom:")) continue;
    const last = groups[groups.length - 1];
    if (last && last[0] === item.group) last[1].push(item);
    else groups.push([item.group, [item]]);
  }

  return (
    <div>
      <div className="proc-head">
        <div>
          <div className="mini-label">Охват проверки</div>
          <div className="proc-head__val">{pct(report.coverage)}</div>
          <div className="proc-head__sub">
            {report.closed} из {report.total} процедур закрыто
          </div>
        </div>
        <div className="proc-head__counts">
          <Count n={report.passed} label="проверено" cls="proc--pass" />
          <Count n={report.findings} label="с находками" cls="proc--finding" />
          <Count n={report.no_data} label="нет данных" cls="proc--nodata" />
          <Count n={report.done} label="выполнено вручную" cls="proc--pass" />
          <Count n={report.skipped} label="снято" cls="proc--skipped" />
          <Count n={report.pending} label="не выполнено" cls="proc--pending" />
        </div>
      </div>

      {/* Границы стоят прямо под охватом: одно без другого вводит в заблуждение. */}
      {report.limits.length > 0 && (
        <div className="proc-limits">
          <div className="proc-limits__title">Границы проверки</div>
          <div className="page-sub" style={{ marginBottom: 8 }}>
            Всё перечисленное попадёт в заключение отдельным разделом. Покупатель
            обязан видеть, что именно не проверялось: умолчание он прочтёт как
            проверенное — скрыть это нельзя.
          </div>
          <ul className="proc-limits__list">
            {report.limits.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
        </div>
      )}

      {groups.map(([group, items]) => (
        <div className="audit-block" key={group}>
          <div className="audit-block__title">{group}</div>
          <div className="proc-list">
            {items.map((item) => {
              const analyst = item.source === "analyst";
              const m = mark(item.code);
              return (
                <div className={"proc " + STATUS[item.status].cls} key={item.code}>
                  <div className="proc__top">
                    <span className="proc__title">{item.title}</span>
                    <span className={"proc__badge " + STATUS[item.status].cls}>
                      {STATUS[item.status].label}
                    </span>
                  </div>
                  <div className="proc__method">
                    {/* Исполнитель — не украшение: он объясняет, почему статус нельзя
                        поставить руками (или наоборот, почему нужно). */}
                    <span className={"proc__who" + (analyst ? " proc__who--analyst" : "")}>
                      {analyst ? "аналитик" : "платформа"}
                    </span>
                    {item.method}
                  </div>
                  {item.detail && <div className="proc__detail">{item.detail}</div>}

                  {analyst ? (
                    <div className="proc__mark">
                      <select
                        className="select"
                        aria-label={`${item.title}: отметка`}
                        value={m.status}
                        onChange={(e) =>
                          setMark(item.code, { status: e.target.value as MarkStatus })}
                      >
                        {MARK_STATUSES.map(([s, label]) => (
                          <option key={s} value={s}>{label}</option>
                        ))}
                      </select>
                      <input
                        className="input"
                        placeholder={m.status === "skipped"
                          ? "Причина снятия (обязательно)"
                          : "Что сделано"}
                        aria-label={`${item.title}: пояснение`}
                        value={m.note}
                        onChange={(e) => setMark(item.code, { note: e.target.value })}
                      />
                    </div>
                  ) : (
                    // Системную процедуру отметить нельзя — и сказано почему, иначе
                    // отсутствие поля читается как недоделка.
                    <div className="proc__locked">
                      Итог выводится из прогона правила — отметить вручную нельзя.
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <div className="audit-block">
        <div className="tab-head" style={{ marginBottom: 10 }}>
          <div className="audit-block__title" style={{ marginBottom: 0 }}>
            Свои процедуры
          </div>
          <Button variant="ghost"
                  onClick={() => onCustom([...custom, emptyCustomProcedure()])}>
            ＋&nbsp;&nbsp;Процедура
          </Button>
        </div>

        <div className="page-sub" style={{ marginBottom: 10 }}>
          Отраслевого каталога у платформы нет намеренно: набор «что проверяют в
          грузоперевозках» — это методика, которой у неё не существует, и выдавать
          придуманный список за неё нельзя. Процедуру, которой платформа не знает,
          пишете вы; ведёте её тоже вы, и в заключении она стоит рядом с базовыми.
        </div>

        {custom.length === 0 ? (
          <div className="field-note">
            Своих процедур нет — чек-лист состоит из каталога.
          </div>
        ) : (
          custom.map((c, i) => (
            <div className="proc-editor" key={i}>
              <input
                className="input proc-editor__title"
                placeholder="Что проверить (например: сверить путевые листы с топливными картами)"
                aria-label={`Своя процедура ${i + 1}: название`}
                value={c.title}
                onChange={(e) => updCustom(i, { title: e.target.value })}
              />
              <select
                className="select"
                aria-label={`Своя процедура ${i + 1}: отметка`}
                value={c.status}
                onChange={(e) => updCustom(i, { status: e.target.value as MarkStatus })}
              >
                {MARK_STATUSES.map(([s, label]) => (
                  <option key={s} value={s}>{label}</option>
                ))}
              </select>
              <input
                className="input"
                placeholder={c.status === "skipped" ? "Причина снятия (обязательно)"
                                                    : "Что сделано"}
                aria-label={`Своя процедура ${i + 1}: пояснение`}
                value={c.note}
                onChange={(e) => updCustom(i, { note: e.target.value })}
              />
              <button type="button" className="icon-action icon-action--danger"
                      title={`Удалить процедуру «${c.title || "без названия"}»`}
                      onClick={() => onCustom(custom.filter((_, k) => k !== i))}>
                <IconTrash size={15} />
              </button>
              {!c.title.trim() && (
                <div className="field-note field-note--warn proc-editor__note">
                  Без названия процедура не существует: в чек-лист и заключение она
                  не попадёт.
                </div>
              )}
              {c.status === "skipped" && !c.note.trim() && (
                <div className="field-note field-note--warn proc-editor__note">
                  Снятие без причины не применяется: процедура, снятая молча,
                  неотличима от забытой — а в «Границах проверки» её обязаны объяснить.
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function Count({ n, label, cls }: { n: number; label: string; cls: string }) {
  if (n === 0) return null;
  return (
    <span className={"proc-count " + cls}>
      <b>{n}</b> {label}
    </span>
  );
}
