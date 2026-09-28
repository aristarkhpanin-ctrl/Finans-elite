import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createApiKey, getApiKeyScope, getApiKeys, revokeApiKey,
         type ApiKey } from "../../api/org";
import { httpDetail } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, Field, Loading, Modal } from "../../components/ui";

/**
 * Ключи доступа к API организации (D5; запись — OPEN-DECISIONS §3).
 *
 * Ключ читает данные организации: выгрузка показателей в BI, отчёт в 1С, свод портфеля.
 * **Право править модели выдаётся при выпуске** и по умолчанию не выдаётся: ключ живёт
 * в чужом сервере, и умолчание обязано быть тем, о чём не пожалеют. Что это значит,
 * экран говорит рядом с самим выбором, а не в документации, которую не откроют: такие
 * правки записаны в журнале на выпустившего, и ключ гаснет вместе с ним.
 *
 * Секрет показывается **один раз**: платформа хранит только отпечаток, и «покажите ещё
 * раз» невозможно ни для кого, включая её саму. Тот же приём, что у резервных кодов
 * второго фактора — и та же обязанность сказать об этом до, а не после.
 */
export function ApiKeysTab({ orgId, canManage }: { orgId: string; canManage: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [writes, setWrites] = useState(false);
  const [issued, setIssued] = useState<{ token: string; note: string } | null>(null);
  const [revoking, setRevoking] = useState<ApiKey | null>(null);

  const { data, isLoading } = useQuery({ queryKey: ["api-keys", orgId],
                                         queryFn: () => getApiKeys(orgId) });
  // Перечень прав приходит с сервера: переписанный здесь своим текстом, он однажды
  // отстал бы, и экран обещал бы ключу то, чего ему давно не выдают.
  const { data: scope } = useQuery({ queryKey: ["api-key-scope", orgId],
                                     queryFn: () => getApiKeyScope(orgId) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["api-keys", orgId] });

  const create = useMutation({
    mutationFn: () => createApiKey(orgId, name.trim(),
                                   writes ? (scope?.grantable ?? []) : []),
    onSuccess: (fresh) => {
      setName("");
      setWrites(false);
      refresh();
      setIssued({ token: fresh.token, note: fresh.scope_note });
    },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось выпустить ключ",
                                   { kind: "error" }),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => revokeApiKey(orgId, id),
    onSuccess: () => { setRevoking(null); refresh(); toast("Ключ отозван",
                                                          { kind: "success" }); },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось отозвать", { kind: "error" }),
  });

  const rows = data ?? [];
  const live = rows.filter((k) => !k.revoked);

  return (
    <div style={{ display: "grid", gap: 18, maxWidth: 720 }}>
      <div className="audit-block">
        <div className="audit-block__title">Ключи доступа к API</div>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Ключ читает данные организации и запускает расчёт — выгрузка в BI, отчёт в 1С,
          свод портфеля. Ключу можно <b>выдать право править модели</b>: такие правки
          записаны в журнале на того, кто выпустил ключ, с пометкой о ключе, и ключ
          перестаёт работать, когда этот человек уходит из организации. Удалять модели и
          писать в обсуждении ключом нельзя. Передаётся заголовком{" "}
          <code>Authorization: Bearer &lt;ключ&gt;</code>.
        </p>

        {isLoading ? <Loading /> : rows.length === 0 ? (
          <div className="mnote">Ключей пока нет.</div>
        ) : (
          <div className="sess-list">
            {rows.map((k) => (
              <div className="sess-row" key={k.id}>
                <div style={{ minWidth: 0 }}>
                  <div className="sess-row__device">
                    {k.name}
                    {k.revoked && <span className="chip chip--blocked"
                                        style={{ height: 20, fontSize: 11 }}>отозван</span>}
                    {/* «Читает» и «правит модели» — разные двери, и в списке это первое,
                        что нужно увидеть. */}
                    {!k.revoked && (
                      <span className={"chip " + (k.writes ? "chip--blocked" : "")}
                            style={{ height: 20, fontSize: 11 }}>
                        {k.writes ? "чтение и запись" : "только чтение"}
                      </span>
                    )}
                  </div>
                  {/* Ключ без автора не работает — и список говорит это, а не показывает
                      живую строку: иначе интеграция считается целой, пока она стоит. */}
                  {!k.revoked && k.author_gone && (
                    <div className="mnote">
                      Не работает: у ключа не осталось действующего автора. Ключ работает
                      от имени выпустившего — выпустите его заново.
                    </div>
                  )}
                  <div className="sess-row__meta">
                    {k.masked} · завёл {k.created_by || "—"} ·{" "}
                    {/* «Ни разу» — это не «давно»: забытый ключ отзывают, а не берегут. */}
                    {k.last_used_at
                      ? `последний раз ${new Date(k.last_used_at).toLocaleDateString("ru-RU")}`
                      : "ни разу не использован"}
                    {k.revoked && k.revoked_by ? ` · отозвал ${k.revoked_by}` : ""}
                  </div>
                </div>
                {!k.revoked && canManage && (
                  <Button variant="ghost" onClick={() => setRevoking(k)}>Отозвать</Button>
                )}
              </div>
            ))}
          </div>
        )}

        {canManage ? (
          <>
            <Field label="Имя нового ключа" value={name} placeholder="Выгрузка в 1С"
                   note="Имя обязательно: через год список безымянных ключей означает, что отозвать можно только все сразу."
                   onChange={(e) => setName(e.target.value)} />
            {/* Выбор прав стоит рядом с выпуском, а не в настройках после него: права
                ключа больше не меняются — нужен другой набор, выпускается другой ключ. */}
            <label className="check" style={{ display: "flex", gap: 8,
                                              alignItems: "flex-start" }}>
              <input type="checkbox" checked={writes}
                     onChange={(e) => setWrites(e.target.checked)} />
              <span>
                Разрешить создавать и править модели проектов и дел
                <span className="field-note" style={{ display: "block" }}>
                  {scope?.note ?? "Права выбираются при выпуске и потом не меняются."}
                </span>
              </span>
            </label>
            <Button onClick={() => create.mutate()} loading={create.isPending}
                    disabled={!name.trim()}>
              Выпустить ключ
            </Button>
            {live.length > 0 && (
              <div className="field-note" style={{ marginTop: 8 }}>
                Действующих ключей: {live.length}. Отзывайте те, о которых уже никто не
                помнит: ключ, чьё назначение забыли, — это открытая дверь без хозяина.
              </div>
            )}
          </>
        ) : (
          <p className="muted" style={{ marginTop: 12 }}>
            🔒 Выпускать и отзывать ключи может владелец организации.
          </p>
        )}
      </div>

      {/* Секрет показывается один раз — и об этом сказано до того, как окно закроют. */}
      <Modal open={issued !== null} title="Ключ выпущен" onClose={() => setIssued(null)}
             maxWidth={560}
             actions={<Button onClick={() => setIssued(null)}>Я сохранил ключ</Button>}>
        <p className="page-sub" style={{ marginTop: 0 }}>
          <b>Скопируйте ключ сейчас.</b> Платформа хранит только его отпечаток и показать
          его ещё раз не сможет — ни вам, ни поддержке. Потеряете — выпустите новый и
          отзовите этот.
        </p>
        <textarea className="input" readOnly rows={3} aria-label="Ключ доступа"
                  style={{ width: "100%", height: "auto", padding: 10,
                           fontFamily: "var(--font-mono)", fontSize: 12 }}
                  value={issued?.token ?? ""}
                  onFocus={(e) => e.currentTarget.select()} />
        <div className="field-note" style={{ marginTop: 10 }}>{issued?.note}</div>
      </Modal>

      <Modal open={revoking !== null} title="Отозвать ключ"
             sub={revoking?.name} maxWidth={440}
             onClose={() => !revoke.isPending && setRevoking(null)}
             actions={
               <>
                 <Button variant="ghost" disabled={revoke.isPending}
                         onClick={() => setRevoking(null)}>Отмена</Button>
                 <Button variant="danger" loading={revoke.isPending}
                         onClick={() => revoking && revoke.mutate(revoking.id)}>
                   Отозвать
                 </Button>
               </>
             }>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Ключ перестанет работать <b>сразу</b> — на следующем же запросе. Всё, что
          ходит с ним (выгрузки, дашборды, интеграции), остановится: убедитесь, что
          знаете, где он используется. В списке ключ останется — с отметкой об отзыве.
        </p>
      </Modal>
    </div>
  );
}
