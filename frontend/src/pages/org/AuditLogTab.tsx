import { useQuery } from "@tanstack/react-query";
import { getAuditLog } from "../../api/org";
import { ErrorState, Loading } from "../../components/ui";

/**
 * Журнал действий организации (макет «Экран 11», раздел «Журнал доступа»; 152-ФЗ).
 *
 * Только чтение. Ни правки, ни удаления у журнала нет — ни в интерфейсе, ни в API:
 * журнал, который можно поправить, не журнал.
 *
 * Записи показываются как есть, включая действия удалённых участников: почта актора
 * хранится в самой записи, поэтому «кто это сделал» читается и через год после ухода.
 */

/** Машинный код действия → человеческая подпись. Незнакомый код показывается как есть. */
const ACTION: Record<string, string> = {
  "member.add": "Добавлен участник",
  "member.role_change": "Изменена роль",
  "member.remove": "Удалён участник",
  "case.create": "Заведено дело",
  "case.duplicate": "Дело дублировано",
  "case.delete": "Дело удалено",
  "case.export": "Выгружен документ",
};

/** Действия, меняющие состав данных или выносящие их наружу, выделяются тоном. */
const TONE: Record<string, string> = {
  "member.remove": "log-row--danger",
  "case.delete": "log-row--danger",
  "case.export": "log-row--attn",
};

function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("ru-RU",
    { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function AuditLogTab({ orgId }: { orgId: string }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["audit-log", orgId],
    queryFn: () => getAuditLog(orgId),
  });

  if (isLoading) return <Loading />;
  if (isError) return <ErrorState text="Не удалось загрузить журнал" onRetry={() => refetch()} />;

  const entries = data?.entries ?? [];

  return (
    <div>
      <div className="page-sub" style={{ marginBottom: 14 }}>
        Действия участников организации. Записи не редактируются и не удаляются;
        срок хранения — 5 лет.
        {data && data.total > entries.length &&
          ` Показаны последние ${entries.length} из ${data.total}.`}
      </div>

      {entries.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">Журнал пуст</div>
          <div className="tab-empty__sub">
            Здесь появятся действия участников: заведение и удаление дел, выгрузка
            документов, изменения состава организации и ролей.
          </div>
        </div>
      ) : (
        <div className="log-list" role="table" aria-label="Журнал действий"
             aria-rowcount={data?.total ?? entries.length}>
          <div className="log-row log-row--head" role="row" aria-rowindex={1}>
            <div role="columnheader">Когда</div>
            <div role="columnheader">Кто</div>
            <div role="columnheader">Что</div>
            <div role="columnheader">Над чем</div>
          </div>
          {entries.map((e, i) => (
            <div className={"log-row " + (TONE[e.action] ?? "")} key={e.id}
                 role="row" aria-rowindex={i + 2}>
              <div className="log-when" role="cell">{when(e.created_at)}</div>
              <div className="log-who" role="rowheader">{e.actor_email || "—"}</div>
              <div role="cell">
                {ACTION[e.action] ?? e.action}
                {e.details && <span className="log-details"> · {e.details}</span>}
              </div>
              <div className="log-entity" role="cell">{e.entity_name || "—"}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
