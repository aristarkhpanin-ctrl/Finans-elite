import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getSupportAccess, grantSupportAccess, revokeSupportAccess,
         type SupportGrant } from "../../api/org";
import { httpDetail } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, Field, Loading, Modal } from "../../components/ui";

/**
 * Доступ поддержки к моделям организации (ADMIN-PHASE-F, F4).
 *
 * Платформа ваших моделей не видит — это её правило, а не любезность. Здесь оно не
 * отменяется: у двери появляется ключ, и ключ **у вас**. Маршрута, которым платформа
 * открыла бы себе доступ сама, не существует ни одного.
 *
 * Экран обязан сказать три вещи до нажатия, а не после: доступ открывается ко **всем**
 * моделям организации (сузить до одной платформа не умеет, и делать вид, что умеет,
 * хуже); сотрудник может только **смотреть**; каждое его обращение к вашим числам
 * попадает в журнал организации **отдельной строкой**.
 */

function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU",
    { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Сколько осталось — числом, а не «скоро»: «до 18:40» читают, «скоро» пропускают. */
function left(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "срок истёк";
  const hours = Math.floor(ms / 3_600_000);
  if (hours >= 1) return `осталось ${hours} ч`;
  return `осталось ${Math.max(1, Math.round(ms / 60_000))} мин`;
}

function GrantRow({ grant }: { grant: SupportGrant }) {
  return (
    <div className="sess-row">
      <div style={{ minWidth: 0 }}>
        <div className="sess-row__device">
          {grant.granted_by_email || "—"}
          <span className={"chip " + (grant.active ? "" : "chip--blocked")}
                style={{ height: 20, fontSize: 11 }}>
            {grant.active ? left(grant.expires_at)
              : grant.revoked_at ? "закрыт" : "истёк"}
          </span>
        </div>
        <div className="sess-row__meta">
          открыт {when(grant.created_at)} · до {when(grant.expires_at)}
          {grant.revoked_at ? ` · закрыт ${when(grant.revoked_at)}` : ""}
          {grant.reason ? ` · ${grant.reason}` : ""}
        </div>
      </div>
    </div>
  );
}

export function SupportAccessTab({ orgId, canManage }:
                                 { orgId: string; canManage: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [hours, setHours] = useState("24");
  const [reason, setReason] = useState("");
  const [closing, setClosing] = useState(false);

  const { data, isLoading } = useQuery({ queryKey: ["support-access", orgId],
                                         queryFn: () => getSupportAccess(orgId) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["support-access", orgId] });

  const open = useMutation({
    mutationFn: () => grantSupportAccess(orgId, Number(hours) || 1, reason.trim()),
    onSuccess: (fresh) => {
      setReason("");
      qc.setQueryData(["support-access", orgId], fresh);
      refresh();
      toast("Доступ открыт", { kind: "success" });
    },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось открыть доступ",
                                   { kind: "error" }),
  });
  const close = useMutation({
    mutationFn: () => revokeSupportAccess(orgId),
    onSuccess: () => { setClosing(false); refresh(); toast("Доступ закрыт",
                                                          { kind: "success" }); },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось закрыть", { kind: "error" }),
  });

  if (isLoading) return <Loading />;

  const current = data?.current ?? null;
  const maxHours = data?.max_hours ?? 72;
  // Закрытые и истёкшие **остаются**: «нам никто не открывал» должно быть проверяемым
  // утверждением, а не отсутствием записи.
  const past = (data?.history ?? []).filter((g) => !g.active);

  return (
    <div style={{ display: "grid", gap: 18, maxWidth: 720 }}>
      <div className="audit-block">
        <div className="audit-block__title">Доступ поддержки к вашим моделям</div>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Платформа <b>не видит содержимого</b> ваших проектов и дел: ей доступны только
          состав организации, тариф и объёмы. Если нужно, чтобы поддержка посмотрела
          модель, доступ открываете вы — на срок не больше {maxHours} ч. Сама платформа
          открыть его себе не может ни одним действием.
        </p>

        {current ? (
          <div className="mnote" role="status">
            <b>Доступ открыт — {left(current.expires_at)}.</b> До {when(current.expires_at)}
            {current.granted_by_email ? `, открыл ${current.granted_by_email}` : ""}
            {current.reason ? `, причина: «${current.reason}»` : ""}.
          </div>
        ) : (
          <div className="mnote">Доступ закрыт: содержимое ваших моделей платформе не видно.</div>
        )}

        {canManage ? (
          <div style={{ marginTop: 14, display: "grid", gap: 10 }}>
            {current ? (
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <Button variant="danger" onClick={() => setClosing(true)}>
                  Закрыть доступ
                </Button>
              </div>
            ) : (
              <>
                <Field label="На сколько часов" type="number" value={hours}
                       note={`Не больше ${maxHours} ч. Доступ, переживший разбор обращения, становится постоянным — и о нём забывают.`}
                       onChange={(e) => setHours(e.target.value)} />
                <Field label="Зачем" value={reason} placeholder="не считается проект «Кофейня»"
                       note="Причина попадёт в журнал и будет видна сотруднику платформы: доступ без причины через неделю неотличим от случайного."
                       onChange={(e) => setReason(e.target.value)} />
                <div>
                  <Button onClick={() => open.mutate()} loading={open.isPending}
                          disabled={reason.trim().length < 3}>
                    Открыть доступ
                  </Button>
                </div>
              </>
            )}
          </div>
        ) : (
          <p className="muted" style={{ marginTop: 12 }}>
            🔒 Открыть и закрыть доступ может владелец или администратор организации.
            Видно его состояние всем участникам: «кто пустил платформу в наши числа» —
            не секрет от тех, чьи это числа.
          </p>
        )}

        {/* Оговорки едут вместе с действием, а не в документации, которую не откроют. */}
        <ul className="mnotes" style={{ marginTop: 14 }}>
          {(data?.notes ?? []).map((n) => <li key={n}>{n}</li>)}
        </ul>
      </div>

      {past.length > 0 && (
        <div className="audit-block">
          <div className="audit-block__title">Раньше открывали</div>
          <p className="page-sub" style={{ marginTop: 0 }}>
            Закрытые и истёкшие доступы остаются здесь: «нам никто не открывал» — это
            проверяемое утверждение, а не отсутствие записи. Что именно смотрели, видно
            в журнале организации.
          </p>
          <div className="sess-list">
            {past.map((g) => <GrantRow grant={g} key={g.id} />)}
          </div>
        </div>
      )}

      <Modal open={closing} title="Закрыть доступ поддержки" maxWidth={440}
             onClose={() => !close.isPending && setClosing(false)}
             actions={
               <>
                 <Button variant="ghost" disabled={close.isPending}
                         onClick={() => setClosing(false)}>Отмена</Button>
                 <Button variant="danger" loading={close.isPending}
                         onClick={() => close.mutate()}>Закрыть доступ</Button>
               </>
             }>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Сотрудники платформы перестанут видеть содержимое ваших моделей сразу.
          Запись о том, что доступ был открыт, останется — вместе со строками журнала
          о том, что именно смотрели.
        </p>
      </Modal>
    </div>
  );
}
