import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { httpDetail, httpStatus } from "../../api/client";
import { useState } from "react";
import { addMember, blockMember, getMembers, issueAccessLink, patchMemberRole, removeMember,
         roleLabel, ROLES, unblockMember, type AccessLink, type Member } from "../../api/org";
import { ESelect } from "../../components/EditorField";
import { IconKey, IconRows, IconTrash, IconWarning } from "../../components/icons";
import { useToast } from "../../components/Toast";
import { Button, Modal, Skeleton } from "../../components/ui";

const AVATAR_BG = ["#5E93FF", "#C77DFF", "var(--primary)", "#E0A23A", "#5FD9A6"];

/** С какого молчания участник считается неактивным — кандидатом на отзыв доступа. */
const INACTIVE_DAYS = 30;

/**
 * Когда участник последний раз работал в организации.
 *
 * `null` — **«неизвестно»**, а не «никогда»: до появления отметки присутствие не
 * записывалось, и выдавать молчание за отсутствие было бы враньём о живом человеке.
 */
function lastSeen(iso: string | null | undefined): { text: string; stale: boolean } {
  if (!iso) return { text: "нет данных", stale: false };
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  const text = days === 0 ? "сегодня"
    : days === 1 ? "вчера"
      : days < 30 ? `${days} дн. назад`
        : new Date(iso).toLocaleDateString("ru-RU",
            { day: "numeric", month: "short", year: "numeric" });
  return { text, stale: days >= INACTIVE_DAYS };
}

const ROLE_DESC: Record<string, string> = {
  owner: "Полный доступ, управление тарифом и участниками. Один на организацию.",
  admin: "Управление проектами и участниками, кроме смены владельца.",
  editor: "Создание и изменение проектов и моделей.",
  analyst: "Создание и расчёт проектов без удаления.",
  viewer: "Только просмотр и расчёт проектов.",
};

/** Роли, назначаемые при приглашении/смене (владелец — только у создателя). */
const ASSIGNABLE = ROLES.filter(([k]) => k !== "owner");

function initials(name: string, fallback: string): string {
  const words = (name || fallback).trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "•";
}

export function MembersTab({ orgId, myRole, myUserId, onShowActions }: {
  orgId: string;
  myRole: string;
  myUserId: string;
  /**
   * Показать действия участника. Ведёт в **журнал** с отбором по нему, а не заводит
   * второй список действий: два источника одних и тех же событий разошлись бы, и
   * пришлось бы гадать, какой из них правда.
   */
  onShowActions?: (email: string) => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const canManage = myRole === "owner" || myRole === "admin";
  const [inviteOpen, setInviteOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("editor");
  const [inviteErr, setInviteErr] = useState("");
  /** Приглашённый, которому нужно передать ссылку активации (пароля у него ещё нет). */
  const [invited, setInvited] = useState<Member | null>(null);
  /** Выданная ссылка входа: приглашение заново или сброс забытого пароля. */
  const [link, setLink] = useState<AccessLink | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  /** Кого приостанавливаем: причина обязательна — блокировка без неё читается как ошибка. */
  const [blockTarget, setBlockTarget] = useState<Member | null>(null);
  const [blockReason, setBlockReason] = useState("");

  const { data, isLoading } = useQuery({ queryKey: ["members", orgId], queryFn: () => getMembers(orgId) });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["members", orgId] });

  const add = useMutation({
    mutationFn: () => addMember(orgId, { email: email.trim(), full_name: fullName.trim(), role }),
    onSuccess: (member) => {
      setInviteOpen(false);
      setEmail("");
      setFullName("");
      setInviteErr("");
      invalidate();
      // Раньше здесь говорилось «Приглашение отправлено» — и это была неправда:
      // почтовой отправки у платформы нет, письмо не уходило никуда, а приглашённый
      // ждал его и не мог войти вовсе. Теперь ссылку активации отдаём пригласившему.
      if (member.invite_token) setInvited(member);
      else toast(`${member.email} добавлен — у него уже есть пароль`, { kind: "success" });
    },
    onError: (e: unknown) => {
      const s = httpStatus(e);
      setInviteErr(
        s === 403
          ? "Недостаточно прав (нужен владелец/администратор)"
          : s === 402
            ? "Достигнут лимит участников тарифа"
            : "Не удалось добавить участника",
      );
    },
  });
  const patch = useMutation({
    mutationFn: ({ uid, r }: { uid: string; r: string }) => patchMemberRole(orgId, uid, r),
    onSuccess: () => {
      invalidate();
      toast("Роль изменена", { kind: "success" });
    },
    onError: () => toast("Не удалось изменить роль", { kind: "error" }),
  });
  const access = useMutation({
    mutationFn: (uid: string) => issueAccessLink(orgId, uid),
    onSuccess: (issued) => setLink(issued),
    // Отказ сервера здесь содержательный (владелец, несколько организаций) — его
    // текст и показываем: своя формулировка разошлась бы с правилом на бэкенде.
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось выдать ссылку",
                                   { kind: "error" }),
  });
  const block = useMutation({
    mutationFn: () => blockMember(orgId, blockTarget!.user_id, blockReason.trim()),
    onSuccess: () => {
      invalidate();
      setBlockTarget(null);
      setBlockReason("");
      toast("Доступ приостановлен", { kind: "success" });
    },
    // Отказы сервера содержательны (владелец, сам себя) — показываем их словами.
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось приостановить доступ",
                                   { kind: "error" }),
  });
  const unblock = useMutation({
    mutationFn: (uid: string) => unblockMember(orgId, uid),
    onSuccess: () => { invalidate(); toast("Доступ возвращён", { kind: "success" }); },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось вернуть доступ",
                                   { kind: "error" }),
  });

  const remove = useMutation({
    mutationFn: (uid: string) => removeMember(orgId, uid),
    onSuccess: () => {
      invalidate();
      setDeleteTarget(null);
      toast("Участник удалён", { kind: "success" });
    },
    onError: () => toast("Не удалось удалить участника", { kind: "error" }),
  });

  return (
    <div>
      <div className="terms-head" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 0 }}>
        <span>Участники{data ? ` (${data.length})` : ""}</span>
        {canManage && (
          <Button onClick={() => { setInviteErr(""); setInviteOpen(true); }}>
            ＋&nbsp;&nbsp;Пригласить участника
          </Button>
        )}
      </div>

      {isLoading && (
        <div className="org-tbl">
          {[0, 1, 2].map((i) => (
            <div className="org-row" key={i}>
              <Skeleton width={200} height={22} />
              <div style={{ flex: 1 }} />
              <Skeleton width={120} height={22} />
            </div>
          ))}
        </div>
      )}

      {data && (
        <div className="org-tbl">
          <div className="org-row org-row--head">
            <div className="org-col-user">Участник</div>
            <div className="org-col-role">Роль</div>
            <div className="org-col-seen">Заходил</div>
            <div className="org-col-status">Статус</div>
            <div className="org-col-act" />
          </div>
          {data.map((m, i) => {
            const isOwner = m.role === "owner";
            const isMe = m.user_id === myUserId;
            const editable = canManage && !isOwner;
            const deletable = canManage && !isOwner && !isMe;
            return (
              <div className="org-row" key={m.user_id}>
                <div className="org-col-user">
                  <div className="org-avatar-lg" style={{ background: AVATAR_BG[i % AVATAR_BG.length] }}>
                    {initials(m.full_name, m.email)}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div className="org-uname">
                      {m.full_name || m.email}
                      {isMe && <span className="you-tag">вы</span>}
                    </div>
                    <div className="org-uemail">{m.email}</div>
                  </div>
                </div>
                <div className="org-col-role">
                  {editable ? (
                    <ESelect label="" value={m.role} onChange={(r) => patch.mutate({ uid: m.user_id, r })} options={ASSIGNABLE} />
                  ) : (
                    <span className="role-badge">
                      {roleLabel(m.role)}
                      {isOwner && (
                        <span className="role-lock" title="Роль владельца изменить нельзя">
                          🔒
                        </span>
                      )}
                    </span>
                  )}
                </div>
                {/* Кто пользуется организацией — это и есть управление лицензиями:
                    место в тарифе занимает тот, кто полгода не появлялся. */}
                <div className="org-col-seen">
                  {(() => {
                    const seen = lastSeen(m.last_seen_at);
                    return (
                      <span className={seen.stale ? "seen-stale" : "seen-fresh"}
                            title={m.last_seen_at
                              ? new Date(m.last_seen_at).toLocaleString("ru-RU")
                              : "Присутствие не отмечалось"}>
                        {seen.text}
                        {seen.stale && <span className="seen-note">не активен</span>}
                      </span>
                    );
                  })()}
                </div>
                <div className="org-col-status">
                  {/* Приостановленный **остаётся в списке**: исчезнувший читался бы как
                      удалённый, а это другое состояние — и другая дорога назад. */}
                  {m.blocked ? (
                    <span className="chip chip--blocked" style={{ height: 22, fontSize: 11 }}
                          title={m.block_reason || "причина не указана"}>
                      приостановлен
                    </span>
                  ) : (
                    <span className="chip chip--active" style={{ height: 22, fontSize: 11 }}>
                      активен
                    </span>
                  )}
                </div>
                <div className="org-col-act">
                  {onShowActions && (
                    <button
                      type="button"
                      className="icon-action"
                      title={`Действия участника: ${m.full_name || m.email}`}
                      onClick={() => onShowActions(m.email)}
                    >
                      <IconRows size={15} />
                    </button>
                  )}
                  {editable && (
                    <button
                      type="button"
                      className="icon-action"
                      title={`Выдать ссылку входа: ${m.full_name || m.email}`}
                      disabled={access.isPending}
                      onClick={() => access.mutate(m.user_id)}
                    >
                      <IconKey size={15} />
                    </button>
                  )}
                  {deletable && (m.blocked ? (
                    <button
                      type="button"
                      className="icon-action"
                      title={`Вернуть доступ: ${m.block_reason || "без причины"}`}
                      disabled={unblock.isPending}
                      onClick={() => unblock.mutate(m.user_id)}
                    >
                      ↩
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="icon-action"
                      title="Приостановить доступ"
                      onClick={() => { setBlockReason(""); setBlockTarget(m); }}
                    >
                      <IconWarning size={15} />
                    </button>
                  ))}
                  {deletable && (
                    <button
                      type="button"
                      className="icon-action icon-action--danger"
                      title="Удалить участника"
                      onClick={() => setDeleteTarget({ id: m.user_id, name: m.full_name || m.email })}
                    >
                      <IconTrash size={15} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {data && data.length === 1 && (
        <p className="muted" style={{ marginTop: 12 }}>
          Вы пока единственный участник организации.
          {canManage && " Пригласите коллег, чтобы работать вместе."}
        </p>
      )}

      {!canManage && (
        <p className="muted" style={{ marginTop: 12, display: "inline-flex", alignItems: "center", gap: 6 }}>
          🔒 Управление участниками доступно владельцу и администраторам.
        </p>
      )}

      {/* RBAC-карточка */}
      <div className="rbac-card">
        <div className="rbac-card__head">О ролях и правах</div>
        <div className="rbac-grid">
          {ROLES.map(([key, label]) => (
            <div className="rbac-item" key={key}>
              <span className="rbac-item__badge">{label}</span>
              <span className="rbac-item__desc">{ROLE_DESC[key]}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Модал приглашения */}
      <Modal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        title="Пригласить участника"
        sub="Пользователь получит доступ к проектам организации согласно выбранной роли."
        maxWidth={460}
        actions={
          <>
            <Button variant="ghost" onClick={() => setInviteOpen(false)}>
              Отмена
            </Button>
            <Button loading={add.isPending} disabled={!email.trim()} onClick={() => add.mutate()}>
              Отправить
            </Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Email</label>
            <input className="input" type="email" placeholder="name@company.ru" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>ФИО</label>
            <input className="input" placeholder="Иван Петров" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div>
            <label className="auth-label" style={{ display: "block", marginBottom: 8 }}>
              Роль
            </label>
            <div className="role-cards">
              {ASSIGNABLE.map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={"role-pick" + (role === key ? " role-pick--on" : "")}
                  onClick={() => setRole(key)}
                >
                  <span className="role-pick__radio" />
                  <span style={{ minWidth: 0 }}>
                    <span className="role-pick__name">{label}</span>
                    <span className="role-pick__desc">{ROLE_DESC[key]}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
          {inviteErr && <div className="field-error">{inviteErr}</div>}
        </div>
      </Modal>

      {/* Приостановка: причина обязательна и её увидит сам участник в отказе. */}
      <Modal open={!!blockTarget} onClose={() => !block.isPending && setBlockTarget(null)}
             title="Приостановить доступ"
             sub={blockTarget ? `${blockTarget.full_name || blockTarget.email} · ${roleLabel(blockTarget.role)}` : undefined}
             maxWidth={460}
             actions={
               <>
                 <Button variant="ghost" disabled={block.isPending}
                         onClick={() => setBlockTarget(null)}>Отмена</Button>
                 <Button variant="danger" loading={block.isPending}
                         disabled={blockReason.trim().length < 3}
                         onClick={() => block.mutate()}>Приостановить</Button>
               </>
             }>
        <div className="page-sub" style={{ marginBottom: 10 }}>
          Участник перестанет работать в этой организации <b>сразу</b> — открытая у него
          вкладка перестанет отвечать на следующем же действии. Роль и история сохранятся,
          доступ возвращается одной кнопкой. В других организациях, если он там состоит,
          он продолжит работать: это решают их администраторы.
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label>Причина</label>
          <input className="input" autoFocus placeholder="напр. увольнение, проверка СБ"
                 aria-label="Причина приостановки"
                 value={blockReason} onChange={(e) => setBlockReason(e.target.value)} />
        </div>
        <div className="field-note" style={{ marginTop: 8 }}>
          Причину увидит сам участник в отказе и любой, кто откроет журнал. Она остаётся
          в журнале навсегда — даже после того, как доступ вернут.
        </div>
      </Modal>

      {/* Модал удаления */}
      <Modal open={!!deleteTarget} onClose={() => !remove.isPending && setDeleteTarget(null)} maxWidth={420}>
        <div style={{ textAlign: "center" }}>
          <div className="modal-danger-ico">
            <IconTrash size={22} />
          </div>
          <h3 className="modal__title">Удалить участника?</h3>
          <div className="modal__sub">
            <b style={{ color: "var(--text)" }}>{deleteTarget?.name}</b> потеряет доступ к проектам
            организации. Проекты и модели останутся.
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <Button variant="ghost" style={{ flex: 1 }} disabled={remove.isPending} onClick={() => setDeleteTarget(null)}>
              Отмена
            </Button>
            <Button variant="danger" style={{ flex: 1 }} loading={remove.isPending} onClick={() => deleteTarget && remove.mutate(deleteTarget.id)}>
              Удалить
            </Button>
          </div>
        </div>
      </Modal>

      {/* Ссылку активации передаёт пригласивший: писем платформа не шлёт, и делать
          вид, что письмо ушло, значит оставить человека ждать его навсегда. */}
      <Modal
        open={invited !== null}
        onClose={() => setInvited(null)}
        title="Передайте ссылку приглашённому"
        sub={invited ? `${invited.email} · ${roleLabel(invited.role)}` : undefined}
        actions={<Button onClick={() => setInvited(null)}>Готово</Button>}
      >
        <div className="page-sub" style={{ marginBottom: 10 }}>
          По этой ссылке участник задаст пароль и войдёт. Ссылка действует неделю и
          срабатывает один раз — писем платформа пока не отправляет, поэтому передайте
          её сами.
        </div>
        <textarea
          className="input"
          readOnly
          rows={3}
          aria-label="Ссылка приглашения"
          style={{ width: "100%", height: "auto", padding: 10, fontFamily: "var(--font-mono)", fontSize: 12 }}
          value={invited ? `${window.location.origin}/activate?token=${invited.invite_token}` : ""}
          onFocus={(e) => e.currentTarget.select()}
        />
      </Modal>

      {/* Ссылка входа, выданная по кнопке: сброс забытого пароля или повторное
          приглашение. Дорога та же самая — участник задаёт пароль и входит. */}
      <Modal
        open={link !== null}
        onClose={() => setLink(null)}
        title={link?.kind === "reset" ? "Ссылка для сброса пароля" : "Ссылка приглашения"}
        sub={link?.email}
        actions={<Button onClick={() => setLink(null)}>Готово</Button>}
      >
        <div className="page-sub" style={{ marginBottom: 10 }}>
          {link?.kind === "reset"
            ? "Участник задаст новый пароль и войдёт. Прежний пароль перестанет "
              + "действовать. Ссылка живёт неделю и срабатывает один раз — если "
              + "участник тем временем сменит пароль сам, она погаснет."
            : "Пароль ещё не заведён — это приглашение заново, взамен потерянного. "
              + "Ссылка действует неделю и срабатывает один раз."}
          {" Писем платформа не отправляет, поэтому передайте её лично."}
        </div>
        <textarea
          className="input"
          readOnly
          rows={3}
          aria-label="Ссылка входа"
          style={{ width: "100%", height: "auto", padding: 10, fontFamily: "var(--font-mono)", fontSize: 12 }}
          value={link ? `${window.location.origin}/activate?token=${link.token}` : ""}
          onFocus={(e) => e.currentTarget.select()}
        />
      </Modal>
    </div>
  );
}
