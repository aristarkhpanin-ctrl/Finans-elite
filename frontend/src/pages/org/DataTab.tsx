import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { deleteOrganization, downloadOrgExport, getOrgDeletePreview,
         type OrgDeletionPlan } from "../../api/org";
import { httpDetail } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { useToast } from "../../components/Toast";
import { Button, ErrorState, Field, Loading, Modal } from "../../components/ui";
import { plural } from "../../format";

/**
 * Забрать всё и уйти (ADMIN-PHASE-F, F6).
 *
 * У человека эти два права закрыты давно (профиль → «Мои данные»), у **организации** не
 * было ни одного: выгрузка существовала только по одному проекту или делу, а закрыть
 * компанию было нельзя вовсе.
 *
 * Экран говорит числа **до** нажатия и не прячет то, что переживёт удаление. Кнопка
 * удаления стоит отдельно и подписана как необратимая: «удалить организацию» рядом с
 * «выгрузить» — это две соседние кнопки, одна из которых стирает работу компании.
 */

export function DataTab({ orgId, orgName, isOwner }:
                        { orgId: string; orgName: string; isOwner: boolean }) {
  const toast = useToast();
  const { refresh } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState("");
  const [exporting, setExporting] = useState(false);

  const preview = useQuery({
    queryKey: ["org-delete-preview", orgId],
    queryFn: () => getOrgDeletePreview(orgId),
    enabled: isOwner,
  });

  const remove = useMutation({
    mutationFn: () => deleteOrganization(orgId, password),
    onSuccess: (done: OrgDeletionPlan) => {
      setConfirming(false);
      setPassword("");
      toast(`Организация «${done.name}» удалена`, { kind: "success" });
      // Список организаций перечитывается: продукт обязан сразу показать то, что
      // осталось, а не ссылаться на арендатора, которого больше нет.
      void refresh();
    },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось удалить организацию",
                                   { kind: "error" }),
  });

  const download = async () => {
    setExporting(true);
    try {
      await downloadOrgExport(orgId, orgName);
      toast("Выгрузка скачана", { kind: "success" });
    } catch (e: unknown) {
      toast(httpDetail(e) ?? "Не удалось выгрузить", { kind: "error" });
    } finally {
      setExporting(false);
    }
  };

  const plan = preview.data;
  return (
    <div style={{ display: "grid", gap: 18, maxWidth: 720 }}>
      <div className="audit-block">
        <div className="audit-block__title">Забрать свои данные</div>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Один файл со всем, что платформа хранит для этой организации: состав, подписки
          и платежи, <b>проекты и дела с моделями целиком</b>, группы, ориентиры,
          чек-листы, обсуждения и журнал доступа. Файл объясняет себя сам — что внутри,
          чего внутри нет и почему.
        </p>
        <ul className="mnotes">
          <li>
            Результатов расчётов внутри нет: они не хранятся, а считаются из модели.
            Отчёты таблицами и документами выгружаются с экранов проектов и дел.
          </li>
          <li>
            Файлов внутри нет: платформа их не хранит вовсе — в обсуждениях сохранены
            ссылки на вашу комнату данных, а не сами материалы.
          </li>
        </ul>
        <Button onClick={download} loading={exporting}>Выгрузить всё в JSON</Button>
      </div>

      {isOwner && (
        <div className="audit-block">
          <div className="audit-block__title">Закрыть организацию</div>
          <p className="page-sub" style={{ marginTop: 0 }}>
            Удаление <b>необратимо</b>: модели проектов и дел, обсуждения и журнал
            исчезнут вместе с организацией. Выгрузите данные до того, как нажмёте.
          </p>

          {preview.isLoading ? <Loading /> : preview.isError || !plan ? (
            <ErrorState text="Не удалось собрать предпросмотр"
                        onRetry={() => preview.refetch()} />
          ) : (
            <>
              <div className="mnote" role="status">
                Исчезнет: {plan.projects}{" "}
                {plural(plan.projects, "проект", "проекта", "проектов")},{" "}
                {plan.cases} {plural(plan.cases, "дело", "дела", "дел")},{" "}
                {plan.comments}{" "}
                {plural(plan.comments, "реплика", "реплики", "реплик")} обсуждений,{" "}
                {plan.log_entries}{" "}
                {plural(plan.log_entries, "запись", "записи", "записей")} журнала
                {plan.api_keys > 0 && `, ${plan.api_keys} ${plural(plan.api_keys,
                  "ключ доступа", "ключа доступа", "ключей доступа")}`}.
              </div>
              {/* Список исключений пустым не бывает: «удалим всё» без него — неправда. */}
              <ul className="mnotes">
                {plan.kept.map((k) => <li key={k}>{k}</li>)}
              </ul>
              <Button variant="danger" onClick={() => setConfirming(true)}>
                Удалить организацию
              </Button>
            </>
          )}
        </div>
      )}

      {!isOwner && (
        <p className="muted">
          🔒 Закрыть организацию может только её владелец. Администратор ведёт
          участников и справочники, но закрытие компании — решение того, кто за неё
          платит.
        </p>
      )}

      <Modal open={confirming} title="Удалить организацию" sub={orgName} maxWidth={480}
             onClose={() => !remove.isPending && setConfirming(false)}
             actions={
               <>
                 <Button variant="ghost" disabled={remove.isPending}
                         onClick={() => setConfirming(false)}>Отмена</Button>
                 <Button variant="danger" loading={remove.isPending}
                         disabled={!password}
                         onClick={() => remove.mutate()}>Удалить навсегда</Button>
               </>
             }>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Это действие <b>нельзя отменить</b>. Всё, что принадлежит организации, будет
          стёрто; учётные записи участников останутся, но эта организация у них исчезнет.
        </p>
        {/* Пароль по тому же доводу, что и при удалении учётной записи: это ровно то,
            что сделает дорвавшийся до открытой вкладки. */}
        <Field label="Ваш пароль" type="password" value={password} autoFocus
               note="Подтверждение паролем: разница между «украли сессию» и «украли компанию» — один запрос."
               onChange={(e) => setPassword(e.target.value)} />
      </Modal>
    </div>
  );
}
