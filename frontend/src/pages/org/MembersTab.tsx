import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { httpStatus } from "../../api/client";
import { useState } from "react";
import { addMember, getMembers, patchMemberRole, removeMember, roleLabel, ROLES,
         type Member } from "../../api/org";
import { ESelect } from "../../components/EditorField";
import { IconTrash } from "../../components/icons";
import { useToast } from "../../components/Toast";
import { Button, Modal, Skeleton } from "../../components/ui";

const AVATAR_BG = ["#5E93FF", "#C77DFF", "var(--primary)", "#E0A23A", "#5FD9A6"];

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

export function MembersTab({ orgId, myRole, myUserId }: { orgId: string; myRole: string; myUserId: string }) {
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
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

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
                <div className="org-col-status">
                  <span className="chip chip--active" style={{ height: 22, fontSize: 11 }}>
                    активен
                  </span>
                </div>
                <div className="org-col-act">
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
    </div>
  );
}
