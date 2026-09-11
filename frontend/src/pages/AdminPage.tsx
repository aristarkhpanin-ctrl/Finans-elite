import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  blockUser,
  getStaffLog,
  getStaffOrgLog,
  getStaffOrganization,
  getStaffOrganizations,
  getPlatformMetrics,
  downloadMetricsCsv,
  resumeOrganization,
  searchStaffUsers,
  suspendOrganization,
  unblockUser,
  type StaffUser,
} from "../api/admin";
import { roleLabel } from "../api/org";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toast";
import { Button, Chip, ErrorState, Field, Loading, Modal } from "../components/ui";
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
 *
 * **Власть оператора над клиентом — два действия** (B2): приостановить организацию и
 * заблокировать учётную запись, у каждого своё снятие. Оба требуют причины, потому что
 * причину увидит тот, кого ограничили. Приостановка **не отбирает данные**: клиент
 * продолжает видеть, считать и выгружать свои модели — это написано и в диалоге, чтобы
 * оператор не думал, будто выключает клиента целиком.
 */

const TABS = [
  ["orgs", "Организации"],
  ["users", "Пользователи"],
  ["metrics", "Сводка"],
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
      {tab === "metrics" && <MetricsTab />}
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
                {o.suspended && <Chip kind="problem">приостановлена</Chip>}
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
  const qc = useQueryClient();
  const toast = useToast();
  const [suspendOpen, setSuspendOpen] = useState(false);
  const [reason, setReason] = useState("");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-org", orgId],
    queryFn: () => getStaffOrganization(orgId),
  });
  const log = useQuery({
    queryKey: ["admin-org-log", orgId],
    queryFn: () => getStaffOrgLog(orgId),
  });

  const suspend = useMutation({
    mutationFn: () => suspendOrganization(orgId, reason.trim()),
    onSuccess: (fresh) => {
      qc.setQueryData(["admin-org", orgId], fresh);
      qc.invalidateQueries({ queryKey: ["admin-orgs"] });
      setSuspendOpen(false);
      setReason("");
      toast("Организация приостановлена", { kind: "success" });
    },
    onError: () => toast("Не удалось приостановить", { kind: "error" }),
  });
  const resume = useMutation({
    mutationFn: () => resumeOrganization(orgId),
    onSuccess: (fresh) => {
      qc.setQueryData(["admin-org", orgId], fresh);
      qc.invalidateQueries({ queryKey: ["admin-orgs"] });
      toast("Приостановка снята", { kind: "success" });
    },
    onError: () => toast("Не удалось снять приостановку", { kind: "error" }),
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
        <div style={{ display: "flex", gap: 8, flex: "none" }}>
          {data.suspended
            ? <Button onClick={() => resume.mutate()} disabled={resume.isPending}>
                Снять приостановку
              </Button>
            : <Button variant="ghost" onClick={() => setSuspendOpen(true)}>
                Приостановить
              </Button>}
        </div>
      </div>

      {/* Состояние приостановки — на самом видном месте карточки, с автором и причиной:
          оператор, снимающий её через месяц, должен видеть, за что она стоит, а не
          восстанавливать это по журналу. */}
      {data.suspended && (
        <div className="restr restr--suspended" role="status">
          <span className="restr__ico" aria-hidden="true">⏸</span>
          <div>
            <div className="restr__title">Организация приостановлена</div>
            <div className="restr__text">
              {data.suspend_reason || "причина не указана"} · {data.suspended_by || "—"},
              {" "}{day(data.suspended_at)}. Клиент видит и выгружает свои данные, править
              их не может.
            </div>
          </div>
        </div>
      )}

      <Modal
        open={suspendOpen}
        title="Приостановить организацию"
        onClose={() => setSuspendOpen(false)}
        actions={
          <>
            <Button variant="ghost" onClick={() => setSuspendOpen(false)}>Отмена</Button>
            <Button onClick={() => suspend.mutate()}
                    disabled={reason.trim().length < 3 || suspend.isPending}>
              Приостановить
            </Button>
          </>
        }
      >
        <p className="page-sub" style={{ marginTop: 0 }}>
          Организация перейдёт в режим чтения и выгрузки: свои модели она видит, считает и
          выгружает, но не заводит и не правит. Данные не отбираются.
        </p>
        <Field label="Причина" value={reason} autoFocus
               onChange={(e) => setReason(e.target.value)}
               note="Причину увидит сама организация — и тот, кто будет снимать приостановку." />
      </Modal>

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
  const qc = useQueryClient();
  const toast = useToast();
  const [q, setQ] = useState("");
  /** Кого блокируем: диалог требует причину — она уйдёт и человеку, и его организациям. */
  const [blocking, setBlocking] = useState<StaffUser | null>(null);
  const [reason, setReason] = useState("");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-users", q],
    queryFn: () => searchStaffUsers(q),
    placeholderData: (prev) => prev,
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-users"] });
  const block = useMutation({
    mutationFn: () => blockUser(blocking!.id, reason.trim()),
    onSuccess: () => {
      refresh();
      setBlocking(null);
      setReason("");
      toast("Учётная запись заблокирована", { kind: "success" });
    },
    onError: () => toast("Не удалось заблокировать", { kind: "error" }),
  });
  const unblock = useMutation({
    mutationFn: (id: string) => unblockUser(id),
    onSuccess: () => {
      refresh();
      toast("Блокировка снята", { kind: "success" });
    },
    onError: () => toast("Не удалось снять блокировку", { kind: "error" }),
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
        «Не могу войти» — это три разных случая: пароль не заводился (приглашение не
        активировано), доступ приостановлен в организации или заблокирована сама учётная
        запись. Ответ различает их.
      </div>

      <Modal
        open={blocking !== null}
        title="Заблокировать учётную запись"
        onClose={() => setBlocking(null)}
        actions={
          <>
            <Button variant="ghost" onClick={() => setBlocking(null)}>Отмена</Button>
            <Button onClick={() => block.mutate()}
                    disabled={reason.trim().length < 3 || block.isPending}>
              Заблокировать
            </Button>
          </>
        }
      >
        <p className="page-sub" style={{ marginTop: 0 }}>
          {blocking?.email} перестанет входить <b>во все организации сразу</b> — это не то
          же, что приостановка участия в одной из них, которую делает её администратор.
          Причину увидит и сам человек, и журналы его организаций.
        </p>
        <Field label="Причина" value={reason} autoFocus
               onChange={(e) => setReason(e.target.value)} />
      </Modal>

      {users.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">Никого не найдено</div>
          <div className="tab-empty__sub">Проверьте адрес или часть имени.</div>
        </div>
      ) : (
        <div className="log-list" role="table" aria-label="Пользователи платформы">
          <div className="log-row adm-row adm-row--head" role="row">
            <div role="columnheader">Пользователь</div>
            <div role="columnheader">Учётная запись</div>
            <div role="columnheader">Организации</div>
            <div role="columnheader">Действия</div>
          </div>
          {users.map((u) => (
            <div className="log-row adm-row" role="row" key={u.id}>
              <div role="rowheader">
                {u.full_name || u.email}
                <div className="adm-sub">{u.email}</div>
                {u.is_staff && <Chip kind="info">сотрудник платформы</Chip>}
              </div>
              <div role="cell">
                {u.blocked
                  ? <Chip kind="problem">
                      заблокирована{u.block_reason ? `: ${u.block_reason}` : ""}
                    </Chip>
                  : u.has_password
                    ? <span className="adm-sub">пароль задан</span>
                    : <Chip kind="warn">пароль не заводился</Chip>}
                <div className="adm-sub">с {day(u.created_at)}</div>
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
              <div role="cell">
                {/* Сотруднику платформы кнопки нет: снимать признак — не отсюда, иначе
                    служебный контур решал бы свои споры блокировками. */}
                {u.is_staff ? <span className="adm-sub">—</span>
                  : u.blocked
                    ? <Button variant="ghost" onClick={() => unblock.mutate(u.id)}
                              disabled={unblock.isPending}>Снять блокировку</Button>
                    : <Button variant="ghost"
                              onClick={() => { setBlocking(u); setReason(""); }}>
                        Заблокировать
                      </Button>}
              </div>
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

/**
 * Сводка платформы (B3): сколько клиентов, кто из них жив, чем пользуются.
 *
 * **Оговорки показываются всегда и рядом с числами**, а не прячутся в подсказку. Ноль
 * выгрузок за период, которого журнал не застал, выглядит ровно как ноль выгрузок; «мы
 * этого не считаем» и «этого не было» — разные утверждения, и различить их может только
 * текст рядом.
 */
function MetricsTab() {
  const toast = useToast();
  const [days, setDays] = useState(30);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-metrics", days],
    queryFn: () => getPlatformMetrics(days),
    placeholderData: (prev) => prev,
  });

  if (isLoading && !data) return <Loading />;
  if (isError || !data) {
    return <ErrorState text="Не удалось собрать сводку" onRetry={() => refetch()} />;
  }

  const growth = data.growth ?? [];
  const peak = Math.max(1, ...growth.map((p) => Math.max(p.organizations, p.users)));

  return (
    <div>
      <div className="log-filter">
        <select className="input" aria-label="Период" value={days}
                onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>За 7 дней</option>
          <option value={30}>За 30 дней</option>
          <option value={90}>За 90 дней</option>
        </select>
        <Button variant="ghost"
                onClick={async () => {
                  try {
                    await downloadMetricsCsv(days);
                    toast("Сводка выгружена", { kind: "success" });
                  } catch {
                    toast("Не удалось выгрузить сводку", { kind: "error" });
                  }
                }}>CSV</Button>
      </div>

      <div className="adm-cards">
        <div className="adm-card">
          <div className="adm-card__label">Организации</div>
          <div className="adm-card__value">{data.organizations}</div>
          <div className="adm-sub">
            активны за 7 дн.: {data.active_organizations?.["7"] ?? 0} ·
            за 30: {data.active_organizations?.["30"] ?? 0}
          </div>
        </div>
        <div className="adm-card">
          <div className="adm-card__label">Пользователи</div>
          <div className="adm-card__value">{data.users}</div>
          <div className="adm-sub">
            активны за 7 дн.: {data.active_users?.["7"] ?? 0} ·
            за 30: {data.active_users?.["30"] ?? 0}
          </div>
          {/* «Без отметки» — не «неактивные»: отметка присутствия ведётся не с
              первого дня, и молчание о человеке ничего о нём не говорит. */}
          {!!data.members_without_mark && (
            <div className="adm-sub">без отметки: {data.members_without_mark}</div>
          )}
        </div>
        <div className="adm-card">
          <div className="adm-card__label">Объёмы</div>
          <div className="adm-card__value">{data.projects} / {data.cases}</div>
          <div className="adm-sub">проектов / дел</div>
        </div>
        <div className="adm-card">
          <div className="adm-card__label">За {data.since_days} дн.</div>
          <div className="adm-card__value">{data.projects_calculated} / {data.exports}</div>
          <div className="adm-sub">проектов считали / выгрузок документов</div>
        </div>
      </div>

      <h2 className="adm-h2" style={{ marginTop: 24 }}>Появлялось по месяцам</h2>
      <div className="mgrid" role="table" aria-label="Рост по месяцам">
        <div className="mgrid__row mgrid__row--head" role="row">
          <div role="columnheader">Месяц</div>
          <div role="columnheader">Организаций</div>
          <div role="columnheader">Пользователей</div>
          <div role="columnheader" aria-hidden="true" />
        </div>
        {growth.map((p) => (
          <div className="mgrid__row" role="row" key={p.period}>
            <div role="rowheader">{p.period}</div>
            <div role="cell">{p.organizations}</div>
            <div role="cell">{p.users}</div>
            {/* Пустой месяц остаётся в ряду с нулём: выброшенный, он превращает провал
                в ровную линию — то есть врёт там, где смотреть интереснее всего. */}
            <div role="cell" aria-hidden="true">
              <span className="mbar" style={{ width: `${(p.users / peak) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>

      <h2 className="adm-h2" style={{ marginTop: 24 }}>Тарифы</h2>
      {(data.plans ?? []).length === 0 ? (
        <div className="page-sub">
          Оформленных подписок нет — все работают на тарифе по умолчанию.
        </div>
      ) : (
        <div className="mgrid" role="table" aria-label="Организации по тарифам">
          <div className="mgrid__row mgrid__row--head" role="row">
            <div role="columnheader">Продукт</div>
            <div role="columnheader">Тариф</div>
            <div role="columnheader">Организаций</div>
            <div role="columnheader" aria-hidden="true" />
          </div>
          {(data.plans ?? []).map((p) => (
            <div className="mgrid__row" role="row" key={p.product + p.plan_code}>
              <div role="rowheader">Финанс-{PRODUCT[p.product] ?? p.product}</div>
              <div role="cell">{p.plan_name}</div>
              <div role="cell">{p.organizations}</div>
              <div role="cell" aria-hidden="true" />
            </div>
          ))}
        </div>
      )}

      <h2 className="adm-h2" style={{ marginTop: 24 }}>Активация</h2>
      <div className="page-sub" style={{ marginTop: 0 }}>
        Сколько организаций дошло до шага — <b>когда-нибудь</b>, а не за период.
      </div>
      <div className="mgrid" role="table" aria-label="Воронка активации">
        <div className="mgrid__row mgrid__row--head" role="row">
          <div role="columnheader">Шаг</div>
          <div role="columnheader">Организаций</div>
          <div role="columnheader">Доля</div>
          <div role="columnheader" aria-hidden="true" />
        </div>
        {(data.funnel ?? []).map((step) => (
          <div className="mgrid__row" role="row" key={step.key}>
            <div role="rowheader">{step.label}</div>
            <div role="cell">{step.organizations}</div>
            {/* Доля от первого шага; без организаций считать не от чего — и тогда
                показывается прочерк, а не «0%». */}
            <div role="cell">
              {step.share == null ? "—" : `${Math.round(step.share * 100)}%`}
            </div>
            <div role="cell" aria-hidden="true">
              <span className="mbar"
                    style={{ width: `${Math.round((step.share ?? 0) * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>

      <h2 className="adm-h2" style={{ marginTop: 24 }}>Удержание</h2>
      {!data.usage_collected ? (
        // Пустой график честнее нарисованного: без событий удержание не измеряется,
        // и «0%» читалось бы как «все ушли».
        <div className="page-sub">
          <b>Не измеряется.</b> Сбор событий пользования выключен (<code>USAGE_EVENTS</code>),
          а отметка присутствия хранит только последнее значение — «вернулся ли человек
          через неделю» из неё не выводится. Включите сбор, и когорты появятся со
          следующего месяца.
        </div>
      ) : (data.retention ?? []).length === 0 ? (
        <div className="page-sub">
          События собираются, но когорт ещё нет: удержание появится, когда пройдёт хотя бы
          один месяц после первых регистраций.
        </div>
      ) : (
        <div className="mgrid" role="table" aria-label="Удержание по когортам">
          <div className="mgrid__row mgrid__row--head" role="row">
            <div role="columnheader">Месяц</div>
            <div role="columnheader">Пришло</div>
            <div role="columnheader">Вернулись</div>
            <div role="columnheader" aria-hidden="true" />
          </div>
          {(data.retention ?? []).map((point) => (
            <div className="mgrid__row" role="row" key={point.month}>
              <div role="rowheader">{point.month}</div>
              <div role="cell">{point.arrived}</div>
              {/* `null` — «не измеряется», а не ноль: ноль читался бы как «все ушли». */}
              <div role="cell">
                {point.returned == null
                  ? <span className="muted">не измеряется</span>
                  : `${point.returned} из ${point.arrived}`}
              </div>
              <div role="cell" aria-hidden="true">
                <span className="mbar" style={{
                  width: point.arrived && point.returned != null
                    ? `${Math.round((point.returned / point.arrived) * 100)}%` : "0%",
                }} />
              </div>
            </div>
          ))}
        </div>
      )}

      <h2 className="adm-h2" style={{ marginTop: 24 }}>Чего эти числа не значат</h2>
      <ul className="mnotes">
        {(data.notes ?? []).map((note) => <li key={note}>{note}</li>)}
      </ul>
    </div>
  );
}
