import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  getStaffLog,
  getStaffOrgLog,
  getStaffOrganization,
  getStaffOrganizations,
  searchStaffUsers,
} from "../api/admin";
import { roleLabel } from "../api/org";
import { useAuth } from "../auth/AuthContext";
import { Button, Chip, ErrorState, Loading } from "../components/ui";
import { plural } from "../format";

/**
 * Служебный раздел платформы (ADMIN-DECOMPOSITION.md, B1).
 *
 * Мы не видели собственных клиентов вовсе: ни списка организаций, ни тарифов, ни ответа
 * на вопрос поддержки «почему человек не может войти». Экран отвечает на эти вопросы — и
 * ровно на них.
 *
 * **Чего здесь нет и не будет:** содержимого проектов и дел. Ни названий, ни чисел
 * модели — правило 6 плана. Оператор видит клиента снаружи; иначе владелец SaaS читает
 * финансовые модели своих клиентов, то есть ровно то, чего клиент и опасается.
 *
 * **Визит виден клиенту.** Открытая карточка организации и прочитанный журнал пишутся в
 * журнал самой организации. Правило «журнал не пишет чтение» защищает его от потока
 * собственных просмотров участников; приход постороннего — событие, которого клиент
 * иначе не увидел бы вовсе, и оговорка об этом стоит прямо на экране: оператор должен
 * знать, что его визит подписан.
 */

const TABS = [
  ["orgs", "Организации"],
  ["users", "Пользователи"],
  ["log", "Журнал сотрудников"],
] as const;

function when(iso: string | null | undefined, dash = "—"): string {
  if (!iso) return dash;
  return new Date(iso).toLocaleString("ru-RU",
    { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function day(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU",
    { day: "numeric", month: "short", year: "numeric" });
}

/** Статус подписки словами. `none` — подписки не было вовсе, это не то же, что бесплатный тариф. */
const SUB_STATUS: Record<string, string> = {
  active: "действует",
  trialing: "пробный период",
  past_due: "просрочена оплата",
  canceled: "отменена",
  none: "подписка не оформлялась",
};

const PRODUCT: Record<string, string> = { business: "Элит", audit: "Аудит" };

export function AdminPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<string>("orgs");
  const [openOrg, setOpenOrg] = useState<string | null>(null);

  // Признак решает только показ. Права проверяет сервер на каждом запросе — интерфейс,
  // который «разрешает», защищает ровно до первого прямого обращения к API.
  if (!user?.is_staff) {
    return (
      <div className="tab-empty">
        <div className="tab-empty__title">Раздел доступен сотрудникам платформы</div>
        <div className="tab-empty__sub">
          Признак сотрудника не выдаётся через интерфейс: маршрут, повышающий права, сам
          стал бы главной мишенью. Его ставит тот, у кого есть доступ к базе.
        </div>
      </div>
    );
  }

  if (openOrg) return <OrgCard orgId={openOrg} onBack={() => setOpenOrg(null)} />;

  return (
    <div>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title">Платформа</h1>
          <div className="page-sub">
            Клиенты, их тарифы и объёмы. Содержимое проектов и дел здесь не показывается —
            и не запрашивается. Открытая карточка организации и прочитанный журнал
            записываются в журнал самого клиента: он видит, что к нему приходили.
          </div>
        </div>
      </div>

      <div className="etabs-wrap" style={{ margin: "0 0 20px", borderTop: "none", padding: 0 }}>
        <div className="etabs">
          {TABS.map(([key, label]) => (
            <button key={key} type="button"
                    className={"etab" + (tab === key ? " etab--active" : "")}
                    onClick={() => setTab(key)}>{label}</button>
          ))}
        </div>
      </div>

      {tab === "orgs" && <OrgsTab onOpen={setOpenOrg} />}
      {tab === "users" && <UsersTab />}
      {tab === "log" && <StaffLogTab />}
    </div>
  );
}

function OrgsTab({ onOpen }: { onOpen: (id: string) => void }) {
  const [q, setQ] = useState("");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-orgs", q],
    queryFn: () => getStaffOrganizations(q),
    placeholderData: (prev) => prev,
  });

  if (isLoading && !data) return <Loading />;
  if (isError) return <ErrorState text="Не удалось загрузить организации"
                                  onRetry={() => refetch()} />;

  const orgs = data?.organizations ?? [];
  return (
    <div>
      <div className="log-filter">
        <input className="input" placeholder="Поиск по названию" aria-label="Поиск организации"
               value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="page-sub" style={{ marginBottom: 12 }}>
        {orgs.length === (data?.total ?? 0)
          ? `${data?.total ?? 0} ${plural(data?.total ?? 0, "организация", "организации", "организаций")}`
          : `Показаны ${orgs.length} из ${data?.total ?? 0}`}
      </div>

      {orgs.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">
            {q ? "По отбору ничего не найдено" : "Организаций нет"}
          </div>
          <div className="tab-empty__sub">
            {q ? "Измените условия поиска." : "Здесь появятся клиенты платформы."}
          </div>
        </div>
      ) : (
        <div className="log-list" role="table" aria-label="Организации платформы">
          <div className="log-row adm-row adm-row--head" role="row">
            <div role="columnheader">Организация</div>
            <div role="columnheader">Тарифы</div>
            <div role="columnheader">Объёмы</div>
            <div role="columnheader">Активность</div>
          </div>
          {orgs.map((o) => (
            <div className="log-row adm-row" role="row" key={o.id}>
              <div role="rowheader">
                <button type="button" className="adm-link" onClick={() => onOpen(o.id)}>
                  {o.name}
                </button>
                <div className="adm-sub">с {day(o.created_at)}</div>
              </div>
              <div role="cell">
                {(o.subscriptions ?? []).map((s) => (
                  <div className="adm-sub" key={s.product}>
                    {PRODUCT[s.product] ?? s.product}: {s.plan_name}
                    {s.status !== "active" && ` · ${SUB_STATUS[s.status] ?? s.status}`}
                  </div>
                ))}
              </div>
              <div role="cell">
                <div className="adm-sub">
                  {o.members} уч.{o.members_blocked ? ` (${o.members_blocked} приост.)` : ""}
                </div>
                <div className="adm-sub">проектов {o.projects} · дел {o.cases}</div>
              </div>
              <div role="cell">
                <div className="adm-sub">заходили: {when(o.last_seen_at, "нет данных")}</div>
                <div className="adm-sub">
                  считали: {when(o.last_calculated_at, "не считали")}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Карточка клиента. Открытие — уже визит: запрос пишется в журнал организации, поэтому
 * карточка не грузится «заодно» со списком, а открывается явным действием.
 */
function OrgCard({ orgId, onBack }: { orgId: string; onBack: () => void }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-org", orgId],
    queryFn: () => getStaffOrganization(orgId),
  });
  const log = useQuery({
    queryKey: ["admin-org-log", orgId],
    queryFn: () => getStaffOrgLog(orgId),
  });

  if (isLoading) return <Loading />;
  if (isError || !data) {
    return <ErrorState text="Не удалось загрузить организацию" onRetry={() => refetch()} />;
  }

  return (
    <div>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <Button variant="ghost" onClick={onBack}>← К списку</Button>
          <h1 className="page-title" style={{ marginTop: 8 }}>{data.name}</h1>
          <div className="page-sub">
            Клиент с {day(data.created_at)}. Ваш визит записан в журнал этой организации.
          </div>
        </div>
      </div>

      <div className="adm-cards">
        {(data.subscriptions ?? []).map((s) => (
          <div className="adm-card" key={s.product}>
            <div className="adm-card__label">«Финанс-{PRODUCT[s.product] ?? s.product}»</div>
            <div className="adm-card__value">{s.plan_name}</div>
            <div className="adm-sub">{SUB_STATUS[s.status] ?? s.status}</div>
            {s.current_period_end && (
              <div className="adm-sub">оплачено до {day(s.current_period_end)}</div>
            )}
          </div>
        ))}
        <div className="adm-card">
          <div className="adm-card__label">Объёмы</div>
          <div className="adm-card__value">{data.projects} / {data.cases}</div>
          <div className="adm-sub">проектов / дел</div>
          <div className="adm-sub">групп {data.groups} · холдингов {data.holdings}</div>
        </div>
        <div className="adm-card">
          <div className="adm-card__label">Последний расчёт</div>
          <div className="adm-card__value">{day(data.last_calculated_at)}</div>
          {/* Числа расчётов нет: счётчика платформа не ведёт, а придуманное число хуже
              отсутствующего. Дата берётся из самих проектов. */}
          <div className="adm-sub">счётчика расчётов платформа не ведёт</div>
        </div>
      </div>

      <h2 className="adm-h2" style={{ marginTop: 24 }}>Участники</h2>
      <div className="log-list" role="table" aria-label="Участники организации">
        <div className="log-row adm-row adm-row--head" role="row">
          <div role="columnheader">Участник</div>
          <div role="columnheader">Роль</div>
          <div role="columnheader">Доступ</div>
          <div role="columnheader">Последний вход</div>
        </div>
        {(data.members_list ?? []).map((m) => (
          <div className="log-row adm-row" role="row" key={m.user_id}>
            <div role="rowheader">
              {m.full_name || m.email}
              <div className="adm-sub">{m.email}</div>
            </div>
            <div role="cell">{roleLabel(m.role)}</div>
            <div role="cell">
              {m.blocked
                ? <Chip kind="problem">приостановлен{m.block_reason ? `: ${m.block_reason}` : ""}</Chip>
                : <Chip kind="active">активен</Chip>}
            </div>
            <div role="cell">{when(m.last_seen_at, "нет данных")}</div>
          </div>
        ))}
      </div>

      <h2 className="adm-h2" style={{ marginTop: 24 }}>Журнал организации</h2>
      <div className="page-sub" style={{ marginBottom: 12 }}>
        Тот же журнал, что видит администратор клиента. Второго представления не заводим:
        расхождение двух ответов на один вопрос пришлось бы разбирать в момент инцидента.
      </div>
      {log.isLoading ? <Loading /> : (
        <div className="log-list" role="table" aria-label="Журнал организации">
          {(log.data?.entries ?? []).map((e) => (
            <div className="log-row adm-row adm-row--log" role="row" key={e.id}>
              <div className="log-when" role="cell">{when(e.created_at)}</div>
              <div className="log-who" role="rowheader">{e.actor_email || "—"}</div>
              <div role="cell">{e.action}{e.details && ` · ${e.details}`}</div>
              <div className="log-entity" role="cell">{e.entity_name || "—"}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function UsersTab() {
  const [q, setQ] = useState("");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-users", q],
    queryFn: () => searchStaffUsers(q),
    placeholderData: (prev) => prev,
  });

  if (isLoading && !data) return <Loading />;
  if (isError) return <ErrorState text="Не удалось загрузить пользователей"
                                  onRetry={() => refetch()} />;

  const users = data ?? [];
  return (
    <div>
      <div className="log-filter">
        <input className="input" placeholder="Поиск по адресу или имени"
               aria-label="Поиск пользователя"
               value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="page-sub" style={{ marginBottom: 12 }}>
        «Не могу войти» — это два разных случая: пароль не заводился (приглашение не
        активировано) или доступ приостановлен. Ответ различает их.
      </div>

      {users.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">Никого не найдено</div>
          <div className="tab-empty__sub">Проверьте адрес или часть имени.</div>
        </div>
      ) : (
        <div className="log-list" role="table" aria-label="Пользователи платформы">
          <div className="log-row adm-row adm-row--head" role="row">
            <div role="columnheader">Пользователь</div>
            <div role="columnheader">Пароль</div>
            <div role="columnheader">Организации</div>
            <div role="columnheader">С какого числа</div>
          </div>
          {users.map((u) => (
            <div className="log-row adm-row" role="row" key={u.id}>
              <div role="rowheader">
                {u.full_name || u.email}
                <div className="adm-sub">{u.email}</div>
                {u.is_staff && <Chip kind="info">сотрудник платформы</Chip>}
              </div>
              <div role="cell">
                {u.has_password
                  ? <span className="adm-sub">задан</span>
                  : <Chip kind="warn">не заводился</Chip>}
              </div>
              <div role="cell">
                {(u.organizations ?? []).length === 0
                  ? <span className="adm-sub">не состоит ни в одной</span>
                  : (u.organizations ?? []).map((o) => (
                      <div className="adm-sub" key={o.id}>
                        {o.name} · {roleLabel(o.role)}
                        {o.blocked && ` · приостановлен${o.block_reason ? `: ${o.block_reason}` : ""}`}
                      </div>
                    ))}
              </div>
              <div role="cell">{day(u.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StaffLogTab() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-staff-log"],
    queryFn: () => getStaffLog(),
  });

  if (isLoading) return <Loading />;
  if (isError) return <ErrorState text="Не удалось загрузить журнал"
                                  onRetry={() => refetch()} />;

  const entries = data?.entries ?? [];
  return (
    <div>
      <div className="page-sub" style={{ marginBottom: 12 }}>
        Где были наши сотрудники. Как и журнал клиента — только чтение: журнал, который
        можно поправить, не журнал, и для собственных следов это верно ровно так же.
      </div>
      {entries.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">Журнал пуст</div>
          <div className="tab-empty__sub">
            Здесь появятся обращения сотрудников платформы к данным клиентов.
          </div>
        </div>
      ) : (
        <div className="log-list" role="table" aria-label="Журнал сотрудников">
          <div className="log-row adm-row adm-row--log adm-row--head" role="row">
            <div role="columnheader">Когда</div>
            <div role="columnheader">Кто</div>
            <div role="columnheader">Что</div>
            <div role="columnheader">У кого</div>
          </div>
          {entries.map((e) => (
            <div className="log-row adm-row adm-row--log" role="row" key={e.id}>
              <div className="log-when" role="cell">{when(e.created_at)}</div>
              <div className="log-who" role="rowheader">{e.actor_email}</div>
              <div role="cell">
                {e.action}
                {e.details && <span className="log-details"> · {e.details}</span>}
              </div>
              <div className="log-entity" role="cell">{e.organization_name || "—"}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
