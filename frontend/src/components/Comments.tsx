import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { addComment, deleteComment, getComments, resolveComment, type Comment,
         type Subject } from "../api/comments";
import { httpDetail } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "./Toast";
import { Button } from "./ui";

/**
 * Обсуждение рядом с числами (D3) — одна панель на оба продукта.
 *
 * Реплика привязана к **месту**: вкладке, строке отчёта, продукту. «Обсуждение проекта»
 * без места — это чат, из которого через месяц не понять, о какой строке шла речь;
 * поэтому подпись места уходит на сервер вместе с репликой и остаётся при ней, даже
 * если объект потом переименуют.
 *
 * Правки текста здесь нет и не будет: отредактированная реплика, на которую уже
 * ответили, переписывает историю. Удалить свою можно — на её месте остаётся
 * «надгробие», потому что пропавшая без следа строка читается как не сказанная никогда.
 */
export function Comments({ subject, anchor = "", anchorLabel = "", title = "Обсуждение" }: {
  subject: Subject;
  /** Место внутри сущности; пусто — общее обсуждение. */
  anchor?: string;
  /** Подпись места **на момент написания** — уходит вместе с репликой. */
  anchorLabel?: string;
  title?: string;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  const [text, setText] = useState("");

  const key = ["comments", subject.kind, subject.id, anchor];
  const { data, isLoading } = useQuery({
    queryKey: key,
    queryFn: () => getComments(subject, anchor || undefined),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: key });

  const say = useMutation({
    mutationFn: () => addComment(subject, text.trim(), anchor, anchorLabel),
    onSuccess: (created) => {
      setText("");
      refresh();
      // Нераспознанное упоминание называется вслух: «позвал, и никто не пришёл» —
      // худший вид тишины.
      if (created.unknown_mentions.length > 0) {
        toast(`В организации нет: ${created.unknown_mentions.join(", ")}. `
              + "Упоминание не сработало.", { kind: "error" });
      } else if (created.notified.length > 0) {
        toast(created.mail.attempted
          ? `Позвали: ${created.notified.join(", ")} — письмо отправлено.`
          : `Позвали: ${created.notified.join(", ")}. Писем платформа не отправляет — `
            + "скажите им сами.", { kind: "success" });
      }
    },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось отправить реплику",
                                   { kind: "error" }),
  });
  const toggle = useMutation({
    mutationFn: ({ id, resolved }: { id: string; resolved: boolean }) =>
      resolveComment(id, resolved),
    onSuccess: refresh,
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось изменить", { kind: "error" }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteComment(id),
    onSuccess: refresh,
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось удалить", { kind: "error" }),
  });

  const rows = data ?? [];
  const open = rows.filter((c) => !c.resolved && !c.deleted).length;

  return (
    <div className="cmt">
      <div className="cmt__head">
        <span className="cmt__title">{title}</span>
        {rows.length > 0 && (
          <span className="cmt__count">
            {open > 0 ? `${open} открыто из ${rows.length}` : `${rows.length} — все закрыты`}
          </span>
        )}
      </div>
      {anchorLabel && <div className="cmt__anchor">{anchorLabel}</div>}

      {isLoading ? (
        <div className="mnote">Загружаем…</div>
      ) : rows.length === 0 ? (
        <div className="mnote">Обсуждения пока нет. Спросите здесь — вопрос останется
          рядом с числами, а не в переписке.</div>
      ) : (
        <div className="cmt__list">
          {rows.map((c) => (
            <CommentRow key={c.id} c={c} mine={c.author_email === user?.email}
                        onResolve={(resolved) => toggle.mutate({ id: c.id, resolved })}
                        onDelete={() => remove.mutate(c.id)} />
          ))}
        </div>
      )}

      <textarea
        className="input cmt__input"
        rows={3}
        aria-label="Новая реплика"
        placeholder="Что обсуждаем? Упомянуть коллегу — @почта@компании.ру"
        value={text}
        disabled={say.isPending}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="cmt__foot">
        {/* Упоминание зовёт посмотреть, но не открывает доступ: обещать иное значило бы
            подменять права на проект строкой в тексте. */}
        <span className="cmt__hint">
          Упоминание зовёт коллегу посмотреть, но прав на проект не даёт.
        </span>
        <Button onClick={() => say.mutate()} loading={say.isPending}
                disabled={!text.trim()}>Отправить</Button>
      </div>
    </div>
  );
}

function CommentRow({ c, mine, onResolve, onDelete }: {
  c: Comment; mine: boolean; onResolve: (resolved: boolean) => void; onDelete: () => void;
}) {
  const when = new Date(c.created_at).toLocaleString("ru-RU",
    { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return (
    <div className={"cmt-row" + (c.resolved ? " cmt-row--done" : "")
                    + (c.deleted ? " cmt-row--gone" : "")}>
      <div className="cmt-row__head">
        <span className="cmt-row__who">{c.author_name || c.author_email}</span>
        <span className="cmt-row__when">{when}</span>
        {/* Подпись места — та, что была на момент написания: объект могли переименовать. */}
        {c.anchor_label && <span className="cmt-row__where">{c.anchor_label}</span>}
        {c.resolved && (
          <span className="status-chip status-chip--ok">
            закрыл {c.resolved_by || "—"}
          </span>
        )}
      </div>
      <div className="cmt-row__body">{c.body}</div>
      {!c.deleted && (
        <div className="cmt-row__acts">
          <button type="button" className="cmt-act"
                  onClick={() => onResolve(!c.resolved)}>
            {c.resolved ? "Открыть заново" : "Вопрос снят"}
          </button>
          {mine && (
            <button type="button" className="cmt-act cmt-act--danger" onClick={onDelete}>
              Удалить
            </button>
          )}
        </div>
      )}
    </div>
  );
}
