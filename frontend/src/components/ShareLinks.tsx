import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { httpDetail } from "../api/client";
import {
  createShareLink, listShareLinks, revokeShareLink, shareUrl, type ShareLink, type ShareLinkCreated,
} from "../api/share";
import { listVersions } from "../api/versions";
import { plural } from "../format";
import { useToast } from "./Toast";
import { Button, Field, Modal, SelectField } from "./ui";

/**
 * «Поделиться» — ссылка для инвестора или банка (пакет L, L4).
 *
 * Ссылка открывает **снимок** проекта без входа. Здесь отправитель решает три вещи — для
 * кого, на какой срок и какую версию, — и видит всё, что уже открыто наружу: кому, до
 * какого числа и сколько раз открывали. Секрет показывается **один раз**, сразу после
 * создания; оговорки (кто открывает — неизвестно, копия не следует за правками) приходят
 * с сервера, своих копий текста здесь нет.
 */

const TERMS: [string, string][] = [
  ["7", "7 дней"],
  ["30", "30 дней"],
  ["90", "90 дней — дольше ссылки не бывает"],
];

function day(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString("ru-RU") : "—";
}

function moment(iso: string | null | undefined): string {
  return iso
    ? new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : "—";
}

/** Состояние ссылки словами: закрытая и истёкшая — разные вещи, и сказано это по-разному. */
export function linkState(link: ShareLink): string {
  if (link.state === "revoked") {
    return `закрыта ${day(link.revoked_at)}` + (link.revoked_by ? ` · ${link.revoked_by}` : "");
  }
  if (link.state === "expired") return `срок истёк ${day(link.expires_at)}`;
  return `открыта до ${day(link.expires_at)}`;
}

/** Сколько раз открывали — из журнала организации; ноль сказан словами, а не цифрой. */
export function linkOpens(link: ShareLink): string {
  if (link.opens === 0) return "ещё не открывали";
  return `открывали ${link.opens} ${plural(link.opens, "раз", "раза", "раз")}, последний — ${moment(link.last_opened_at)}`;
}

export function ShareLinks({ open, onClose, projectId }: {
  open: boolean;
  onClose: () => void;
  projectId: string;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [label, setLabel] = useState("");
  const [days, setDays] = useState("30");
  const [version, setVersion] = useState("");
  const [created, setCreated] = useState<ShareLinkCreated | null>(null);

  const links = useQuery({
    queryKey: ["share-links", projectId], queryFn: () => listShareLinks(projectId), enabled: open,
  });
  const versions = useQuery({
    queryKey: ["versions", projectId], queryFn: () => listVersions(projectId), enabled: open,
  });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["share-links", projectId] });
    void qc.invalidateQueries({ queryKey: ["versions", projectId] });
  };
  const create = useMutation({
    mutationFn: () => createShareLink(projectId, {
      label: label.trim(), days: Number(days), version_id: version || null,
    }),
    onSuccess: (link) => {
      setCreated(link);
      setLabel("");
      refresh();
    },
  });
  const revoke = useMutation({
    mutationFn: (linkId: string) => revokeShareLink(projectId, linkId),
    onSuccess: () => {
      toast("Ссылка закрыта — по ней план больше не откроется", { kind: "success" });
      refresh();
    },
    onError: (e) => toast(httpDetail(e) ?? "Не удалось закрыть ссылку", { kind: "error" }),
  });

  const close = () => {
    setCreated(null);
    create.reset();
    onClose();
  };
  const url = created ? shareUrl(created.path) : "";
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      toast("Ссылка скопирована", { kind: "success" });
    } catch {
      // Буфер обмена недоступен (нет разрешения, старый браузер) — поле выделяется само
      // при фокусе, и скопировать можно руками.
      toast("Скопируйте ссылку из поля вручную", { kind: "warn" });
    }
  };

  const versionOptions: [string, string][] = [
    ["", "Текущий план — снимок сделается сейчас"],
    ...(versions.data ?? []).map((v): [string, string] => [v.id, v.label]),
  ];
  const all = links.data?.links ?? [];

  return (
    <Modal open={open} onClose={close} title="Ссылка для инвестора или банка" maxWidth={720}
           sub="План откроется без входа и регистрации: показатели, отчёты и бизнес-план в DOCX"
           actions={<Button variant="ghost" onClick={close}>Готово</Button>}>
      {created ? (
        <div className="share-created" role="status">
          <div className="share-created__title">Ссылка для «{created.label}» готова</div>
          <div className="share-created__row">
            <Field label="Ссылка" value={url} readOnly onFocus={(e) => e.currentTarget.select()} />
            <Button onClick={copy}>Копировать</Button>
          </div>
          <ul className="share-notes">
            {created.notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
          <Button variant="link" onClick={() => setCreated(null)}>Сделать ещё одну</Button>
        </div>
      ) : (
        <form className="share-form" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Field label="Для кого" value={label} maxLength={200} autoFocus
                 placeholder="Например: Сбербанк, кредитный комитет"
                 onChange={(e) => setLabel(e.target.value)}
                 note="Имя печатается на копии: «Копия для: …»." />
          <div className="share-form__row">
            <SelectField label="Срок" value={days} onChange={setDays} options={TERMS} />
            <SelectField label="Что открыть" value={version} onChange={setVersion}
                         options={versionOptions} />
          </div>
          {create.isError && (
            <div className="field-note field-note--warn" role="alert">
              {httpDetail(create.error) ?? "Не удалось открыть ссылку. Попробуйте ещё раз."}
            </div>
          )}
          <Button type="submit" loading={create.isPending} disabled={!label.trim()}>
            Открыть ссылку
          </Button>
        </form>
      )}

      <h4 className="share-list__title">
        Ссылки этого проекта{all.length > 0 ? ` · ${all.length}` : ""}
      </h4>
      {links.isError && (
        <div className="field-note field-note--warn" role="alert">
          {httpDetail(links.error) ?? "Не удалось загрузить ссылки."}
        </div>
      )}
      {links.data && all.length === 0 && (
        <div className="field-note">Ссылок ещё не открывали — план видят только участники организации.</div>
      )}
      {all.length > 0 && (
        <div className="share-list">
          {all.map((link) => (
            <div key={link.id} className={"share-row" + (link.state !== "active" ? " share-row--off" : "")}>
              <div style={{ minWidth: 0 }}>
                <div className="share-row__who">{link.label}</div>
                <div className="share-row__meta">
                  {linkState(link)} · версия «{link.version_label}» · {linkOpens(link)}
                </div>
                <div className="share-row__meta">открыл {link.created_by} {day(link.created_at)}</div>
              </div>
              {link.state === "active" && (
                <Button variant="ghost" loading={revoke.isPending && revoke.variables === link.id}
                        onClick={() => revoke.mutate(link.id)}
                        aria-label={`Закрыть ссылку для «${link.label}»`}>
                  Закрыть
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
      {links.data && (
        <ul className="share-notes">
          {links.data.notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
      )}
    </Modal>
  );
}
