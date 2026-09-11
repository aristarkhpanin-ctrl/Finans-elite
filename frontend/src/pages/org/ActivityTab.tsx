import { useQuery } from "@tanstack/react-query";
import { getActivity, roleLabel } from "../../api/org";
import { Loading } from "../../components/ui";

/**
 * Активность организации (E1): кто работает и что живо.
 *
 * Экран отвечает на вопрос, который владелец задаёт вслух: «кто у меня работает и за
 * что я плачу». Новых счётчиков под него не заводилось — всё собрано из отметок
 * присутствия, журнала и дат последнего расчёта, поэтому сводка не может разойтись с
 * другими экранами.
 *
 * **Границы едут вместе с числами.** Без них сводка читается как отчёт о людях: пустое
 * «заходил» превращается в «не работает», а «действий 0» — в «бездельничает». Платформа
 * не знает ни того, ни другого: присутствие отмечается раз в час и не с первого дня,
 * а чтение журнал не пишет.
 */
export function ActivityTab({ orgId }: { orgId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["activity", orgId],
    queryFn: () => getActivity(orgId),
  });

  if (isLoading) return <Loading />;
  if (isError || !data) {
    return <div className="mnote">Не удалось загрузить сводку активности.</div>;
  }

  const sleeping = data.entities.filter((e) => e.stale).length;
  const questions = data.entities.reduce((s, e) => s + e.open_comments, 0);

  return (
    <div style={{ display: "grid", gap: 18, maxWidth: 820 }}>
      <div className="audit-block">
        <div className="audit-block__title">Кто работает</div>
        <div className="page-sub" style={{ marginTop: 0 }}>
          Действия — за последние {data.window_days} дн.
        </div>
        <div className="org-tbl" style={{ marginTop: 10 }}>
          <div className="org-row org-row--head">
            <div className="org-col-user">Участник</div>
            <div className="org-col-role">Роль</div>
            <div className="org-col-seen">Заходил</div>
            <div className="org-col-status">Действий</div>
          </div>
          {data.members.map((m) => (
            <div className="org-row" key={m.user_id}>
              <div className="org-col-user">
                <div style={{ minWidth: 0 }}>
                  <div className="org-uname">{m.full_name || m.email}</div>
                  <div className="org-uemail">{m.email}</div>
                </div>
              </div>
              <div className="org-col-role">
                <span className="role-badge">{roleLabel(m.role)}</span>
              </div>
              <div className="org-col-seen">
                {/* Пусто — «неизвестно», а не «никогда»: отметка ведётся не с первого дня. */}
                {m.last_seen_at
                  ? new Date(m.last_seen_at).toLocaleDateString("ru-RU",
                      { day: "numeric", month: "short", year: "numeric" })
                  : <span className="muted">нет данных</span>}
              </div>
              <div className="org-col-status">
                <span className={m.actions > 0 ? "seen-fresh" : "seen-stale"}>
                  {m.actions}
                </span>
                {m.blocked && (
                  <span className="chip chip--blocked" style={{ height: 20, fontSize: 11 }}>
                    приостановлен
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="audit-block">
        <div className="audit-block__title">Что живо</div>
        <div className="page-sub" style={{ marginTop: 0 }}>
          {data.entities.length === 0
            ? "Проектов и дел пока нет."
            : <>Всего {data.entities.length}; не трогали дольше {data.stale_days} дн.:{" "}
               <b>{sleeping}</b>; открытых обсуждений: <b>{questions}</b>.</>}
        </div>
        {data.entities.length > 0 && (
          <div className="org-tbl" style={{ marginTop: 10 }}>
            <div className="org-row org-row--head">
              <div className="org-col-user">Название</div>
              <div className="org-col-role">Что это</div>
              <div className="org-col-seen">Правили</div>
              <div className="org-col-status">Считали</div>
              <div className="org-col-act">Вопросов</div>
            </div>
            {data.entities.map((e) => (
              <div className="org-row" key={`${e.kind}:${e.id}`}>
                <div className="org-col-user">
                  <div className="org-uname">
                    {e.name}
                    {e.stale && <span className="seen-note">спит</span>}
                  </div>
                </div>
                <div className="org-col-role">
                  <span className="role-badge">
                    {e.kind === "project" ? "Проект" : "Дело"}
                  </span>
                </div>
                <div className="org-col-seen">
                  {e.updated_at
                    ? new Date(e.updated_at).toLocaleDateString("ru-RU",
                        { day: "numeric", month: "short" })
                    : "—"}
                </div>
                <div className="org-col-status">
                  {/* Число расчётов платформа не ведёт — только дату последнего. */}
                  {e.last_calculated_at
                    ? new Date(e.last_calculated_at).toLocaleDateString("ru-RU",
                        { day: "numeric", month: "short" })
                    : <span className="muted">—</span>}
                </div>
                <div className="org-col-act">
                  {e.open_comments > 0 ? e.open_comments : ""}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Границы — рядом с числами, а не в документации: сводка без них обещает
          больше, чем платформа знает. */}
      <ul className="mnotes">
        {data.notes.map((n) => <li key={n}>{n}</li>)}
      </ul>
    </div>
  );
}
