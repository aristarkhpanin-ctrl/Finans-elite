import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { deleteOrgLogo, fileToBase64, getOrgLogo, MAX_LOGO_BYTES, setOrgLogo,
         type OrgLogo } from "../../api/branding";
import { httpDetail, httpFieldError } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, ErrorState, Loading } from "../../components/ui";

/**
 * Оформление организации (пакет L, L9): логотип на титуле документов и в шапке печати.
 *
 * Консультант отдаёт план клиенту под своим именем. Правила приёма — **с сервера**
 * (`rules`): экран их показывает, а не пересказывает своими словами, иначе вторая
 * формулировка однажды разошлась бы с проверкой. Отказ тоже приходит с сервера и
 * называет причину — «SVG не принимается, потому что…», а не «не тот формат».
 */

function kib(bytes: number): string {
  return `${Math.max(1, Math.ceil(bytes / 1024))} КБ`;
}

function when(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString("ru-RU") : "—";
}

function Meta({ logo }: { logo: OrgLogo }) {
  return (
    <div className="brand-meta">
      {logo.kind} · {kib(logo.size ?? 0)} · {logo.width}×{logo.height} px
      {logo.updated_by ? ` · поставил ${logo.updated_by}` : ""}
      {logo.updated_at ? `, ${when(logo.updated_at)}` : ""}
    </div>
  );
}

export function BrandingTab({ orgId, orgName, canManage }:
                            { orgId: string; orgName: string; canManage: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["org-logo", orgId], queryFn: () => getOrgLogo(orgId),
  });

  const upload = useMutation({
    mutationFn: async (file: File) => setOrgLogo(orgId, await fileToBase64(file)),
    onSuccess: (fresh) => {
      qc.setQueryData(["org-logo", orgId], fresh);
      toast("Логотип поставлен — он появится в следующих документах", { kind: "success" });
    },
    // Причина — с сервера: «SVG не принимается: в нём бывает исполняемый код…».
    onError: (e: unknown) => toast(httpDetail(e) ?? httpFieldError(e)
                                   ?? "Не удалось поставить логотип", { kind: "error" }),
  });
  const remove = useMutation({
    mutationFn: () => deleteOrgLogo(orgId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-logo", orgId] });
      toast("Логотип убран — документы выходят с маркой платформы", { kind: "success" });
    },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось убрать логотип",
                                   { kind: "error" }),
  });

  if (isLoading) return <Loading />;
  if (isError || !data) {
    return <ErrorState text="Не удалось загрузить оформление" sub={httpDetail(error) ?? undefined}
                       onRetry={() => refetch()} />;
  }

  const limit = data.max_bytes ?? MAX_LOGO_BYTES;
  const pick = (file: File) => {
    // Мегабайты в сеть не отправляем: предел назван сервером, отказ здесь — тем же числом.
    if (file.size > limit) {
      toast(`Логотип больше ${kib(limit)} (${kib(file.size)}) — уменьшите файл`,
            { kind: "warn" });
      return;
    }
    upload.mutate(file);
  };

  return (
    <div style={{ display: "grid", gap: 18, maxWidth: 720 }}>
      <div className="audit-block">
        <h2 className="audit-block__title">Логотип в документах</h2>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Бизнес-план, заключение по делу и печатный бланк выходят под вашим логотипом —
          их отдают клиенту и банку от имени организации, а не платформы.
        </p>

        {data.present && data.data_url ? (
          <div className="brand-preview">
            {/* Лист бумаги: логотип показан так, как ляжет на титул, — на белом в обеих
                темах. Подписи вне листа: на белом тёмная тема их бы потеряла. */}
            <div className="brand-preview__paper">
              <img className="brand-preview__img" src={data.data_url}
                   alt={`Логотип «${orgName}»`} />
            </div>
            <Meta logo={data} />
          </div>
        ) : (
          <div className="mnote">
            Логотипа нет — документы выходят с маркой платформы.
          </div>
        )}

        {canManage ? (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 14 }}>
            <Button onClick={() => fileRef.current?.click()} loading={upload.isPending}>
              {data.present ? "Заменить логотип" : "Загрузить PNG или JPEG"}
            </Button>
            {data.present && (
              <Button variant="ghost" onClick={() => remove.mutate()}
                      loading={remove.isPending}>
                Убрать логотип
              </Button>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg"
              aria-label="Файл логотипа"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) pick(file);
                e.target.value = "";          // тот же файл можно выбрать снова
              }}
            />
          </div>
        ) : (
          <p className="muted" style={{ marginTop: 12 }}>
            🔒 Поставить или убрать логотип может владелец или администратор организации:
            он подписывает документы, которые уходят от её имени.
          </p>
        )}

        <ul className="mnotes" style={{ marginTop: 14 }}>
          {(data.rules ?? []).map((rule) => <li key={rule}>{rule}</li>)}
        </ul>
      </div>
    </div>
  );
}
