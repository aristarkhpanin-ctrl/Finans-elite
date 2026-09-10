import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { downloadAuditLogCsv, getAuditLog, type AuditLogFilter } from "../../api/org";
import { IconDownload } from "../../components/icons";
import { useToast } from "../../components/Toast";
import { Button, ErrorState, Loading } from "../../components/ui";

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
  "org.create": "Заведена организация",
  "member.add": "Добавлен участник",
  "member.role_change": "Изменена роль",
  "member.remove": "Удалён участник",
  "member.block": "Доступ приостановлен",
  "member.unblock": "Доступ возвращён",
  "member.access_link": "Выдана ссылка входа",
  "benchmarks.replace": "Изменены отраслевые ориентиры",
  "billing.checkout": "Смена тарифа через оплату",
  "billing.plan_change": "Изменён тариф",
  "audit_log.export": "Журнал выгружен",
  // «Финанс-Элит»
  "project.create": "Создан проект",
  "project.update": "Изменён проект",
  "project.delete": "Удалён проект",
  "project.duplicate": "Проект дублирован",
  "project.finalize": "План финализирован",
  "project.export": "Выгружен бизнес-план",
  "project.version": "Снята версия проекта",
  "project.version_delete": "Удалена версия проекта",
  "project.version_restore": "Восстановлена версия проекта",
  "holding.create": "Создан холдинг",
  "holding.delete": "Удалён холдинг",
  // «Финанс-Аудит»
  "case.create": "Заведено дело",
  "case.update": "Изменено дело",
  "case.duplicate": "Дело дублировано",
  "case.delete": "Дело удалено",
  "case.export": "Выгружен документ",
  "case.version": "Снята версия дела",
  "case.version_delete": "Удалена версия дела",
  "case.version_restore": "Восстановлена версия дела",
  "group.create": "Создана группа",
  "group.update": "Изменена группа",
  "group.delete": "Удалена группа",
  // Вход и пароль
  "auth.login": "Вход в систему",
  "auth.login_failed": "Неудачная попытка входа",
  "auth.activate": "Активирована ссылка входа",
  "auth.password_change": "Изменён пароль",
  "auth.password_change_failed": "Неудачная смена пароля",
};

/** Действия, меняющие состав данных или выносящие их наружу, выделяются тоном. */
const TONE: Record<string, string> = {
  "member.remove": "log-row--danger",
  "member.block": "log-row--danger",
  "case.delete": "log-row--danger",
  "project.delete": "log-row--danger",
  "holding.delete": "log-row--danger",
  "group.delete": "log-row--danger",
  "auth.login_failed": "log-row--danger",
  "auth.password_change_failed": "log-row--danger",
  // Вынос данных наружу — не ошибка, но и не рядовое событие.
  "case.export": "log-row--attn",
  "project.export": "log-row--attn",
  "audit_log.export": "log-row--attn",
};

function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("ru-RU",
    { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function AuditLogTab({ orgId, initialActor = "" }: {
  orgId: string;
  /** С кого начать отбор — приходит с экрана участников («действия участника»). */
  initialActor?: string;
}) {
  const toast = useToast();
  /** Отбор — в состоянии страницы: он же уходит и в выгрузку, чтобы файл совпал с экраном. */
  const [filter, setFilter] = useState<AuditLogFilter>(
    initialActor ? { actor: initialActor } : {});
  const set = (patch: AuditLogFilter) => setFilter({ ...filter, ...patch });

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ["audit-log", orgId, filter],
    queryFn: () => getAuditLog(orgId, filter),
    // Прошлая страница остаётся, пока грузится новая: иначе смена отбора уносила бы
    // в спиннер весь экран **вместе с панелью отбора** — поле поиска исчезало бы из-под
    // рук на каждом нажатии клавиши.
    placeholderData: (prev) => prev,
  });

  if (isLoading && !data) return <Loading />;
  if (isError) return <ErrorState text="Не удалось загрузить журнал" onRetry={() => refetch()} />;

  const entries = data?.entries ?? [];

  return (
    <div>
      <div className="page-sub" style={{ marginBottom: 12 }}>
        Действия участников организации. Записи не редактируются и не удаляются;
        срок хранения — 5 лет.
        {data && data.total > entries.length &&
          ` Показаны последние ${entries.length} из ${data.total} по текущему отбору.`}
        {isFetching && <span className="log-fetching"> Обновляем…</span>}
      </div>

      {/* Отбор: без него журнал на двадцать тысяч записей есть, а ответа из него не
          достать. Предлагается встречавшееся, а не весь каталог кодов. */}
      <div className="log-filter">
        <input className="input" placeholder="Поиск: объект, участник, примечание"
               aria-label="Поиск по журналу"
               value={filter.q ?? ""} onChange={(e) => set({ q: e.target.value })} />
        <select className="input" aria-label="Участник"
                value={filter.actor ?? ""} onChange={(e) => set({ actor: e.target.value })}>
          <option value="">Все участники</option>
          {(data?.actors ?? []).map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select className="input" aria-label="Действие"
                value={filter.action ?? ""} onChange={(e) => set({ action: e.target.value })}>
          <option value="">Все действия</option>
          {(data?.actions ?? []).map((a) => (
            <option key={a} value={a}>{ACTION[a] ?? a}</option>
          ))}
        </select>
        <input className="input" type="date" aria-label="С даты"
               value={(filter.since ?? "").slice(0, 10)}
               onChange={(e) => set({ since: e.target.value ? `${e.target.value}T00:00:00` : "" })} />
        <input className="input" type="date" aria-label="По дату"
               value={(filter.until ?? "").slice(0, 10)}
               onChange={(e) => set({ until: e.target.value ? `${e.target.value}T23:59:59` : "" })} />
        <Button variant="ghost" onClick={() => setFilter({})}>Сбросить</Button>
        <Button variant="ghost"
                onClick={async () => {
                  try {
                    await downloadAuditLogCsv(orgId, filter);
                    toast("Журнал выгружен", { kind: "success" });
                  } catch {
                    toast("Не удалось выгрузить журнал", { kind: "error" });
                  }
                }}>
          <IconDownload size={15} />
          <span style={{ marginLeft: 6 }}>CSV</span>
        </Button>
      </div>

      {entries.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">
            {Object.values(filter).some(Boolean) ? "По отбору ничего не найдено" : "Журнал пуст"}
          </div>
          <div className="tab-empty__sub">
            {Object.values(filter).some(Boolean)
              ? "Измените условия отбора или сбросьте их."
              : "Здесь появятся действия участников: работа с проектами и делами, выгрузка "
                + "документов, изменения состава организации, входы в систему."}
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
