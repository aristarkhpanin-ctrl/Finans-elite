import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { getGirboPreview, type AuditModel, type GirboPreview } from "../api/audit";
import { httpDetail } from "../api/client";
import { fmtDateOnly, fmtMillions } from "../format";
import { applyGirbo, yearSummary, type GirboApplyResult } from "../girboImport";
import { Button, Field, Modal, ScrollRegion } from "./ui";

/**
 * Отчётность фирмы-цели по ИНН из ГИР БО (пакет L, L3).
 *
 * Два шага: **найти** (сервер спрашивает ресурс ФНС и сопоставляет строки) и **заменить**
 * отчётность дела — модель меняется на экране, а сохраняет её человек. До замены видно
 * всё, что важно решить: чья это отчётность, действует ли организация, какие годы и в
 * какой форме, и что при загрузке отнесено куда. Оговорки — с сервера, своих копий здесь
 * нет.
 */
export function GirboImport({ open, onClose, model, onApply }: {
  open: boolean;
  onClose: () => void;
  model: AuditModel;
  onApply: (result: GirboApplyResult) => void;
}) {
  const [inn, setInn] = useState(model.report?.subject_inn || model.registry?.inn || "");
  const [fill, setFill] = useState(true);
  const find = useMutation<GirboPreview, unknown, string>({ mutationFn: getGirboPreview });
  const preview = find.data;
  const inactive = preview && preview.registry.status_code !== "ACTIVE";

  const apply = () => {
    if (!preview) return;
    onApply(applyGirbo(model, preview, { fillRequisites: fill }));
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title="Отчётность по ИНН из ГИР БО" maxWidth={760}
           sub="Ресурс бухгалтерской отчётности ФНС: баланс и отчёт о финансовых результатах"
           actions={(
             <>
               <Button variant="ghost" onClick={onClose}>Отмена</Button>
               <Button onClick={apply} disabled={!preview}>Заменить отчётность дела</Button>
             </>
           )}>
      <form className="girbo-find" onSubmit={(e) => { e.preventDefault(); find.mutate(inn.trim()); }}>
        <Field label="ИНН организации" value={inn} inputMode="numeric" maxLength={12}
               onChange={(e) => setInn(e.target.value.replace(/\D/g, ""))}
               note="Запрос уходит с сервера платформы на bo.nalog.gov.ru." />
        <Button type="submit" variant="ghost" loading={find.isPending}
                disabled={inn.trim().length < 10}>Найти</Button>
      </form>

      {find.isError && (
        <div className="field-note field-note--warn" role="alert">
          {httpDetail(find.error) ?? "Не удалось загрузить отчётность. Попробуйте позже."}
        </div>
      )}

      {preview && (
        <div className="girbo-preview">
          <div className="girbo-preview__head">
            <b>{preview.registry.full_name || preview.registry.short_name}</b>
            <span>ИНН {preview.registry.inn} · ОГРН {preview.registry.ogrn}</span>
            {preview.registry.okved && <span>{preview.registry.okved}</span>}
            <span className={inactive ? "girbo-preview__status--bad" : ""}>
              Статус: {preview.status_label}
              {preview.registry.status_date ? ` с ${fmtDateOnly(preview.registry.status_date)}` : ""}
              {" · "}сведения на {fmtDateOnly(preview.registry.fetched_on)}
            </span>
          </div>
          {inactive && (
            <div className="field-note field-note--warn" role="note">
              Организация недействующая по сведениям ресурса — в деле это станет флагом риска.
              Проверьте выписку ЕГРЮЛ.
            </div>
          )}
          <ScrollRegion className="x-scroll" label="Годы отчётности из ГИР БО">
            <table className="audit-grid">
              <thead>
                <tr>
                  <th className="audit-grid__rowhead">Год</th>
                  <th>Форма</th><th>Выручка</th><th>Чистая прибыль</th><th>Итог баланса</th>
                </tr>
              </thead>
              <tbody>
                {preview.periods.map((p, t) => {
                  const s = yearSummary(preview, t);
                  return (
                    <tr key={p}>
                      <th className="audit-grid__rowhead" title={preview.sources[t]}>{p}</th>
                      <td>{preview.forms[t]}</td>
                      <td>{fmtMillions(s.revenue, { digits: 2 })}</td>
                      <td>{fmtMillions(s.net, { digits: 2 })}</td>
                      <td>{fmtMillions(s.assets, { digits: 2 })}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </ScrollRegion>
          <ul className="girbo-preview__notes" aria-label="Оговорки загрузки">
            {preview.notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
          <label className="auth-remember">
            <input type="checkbox" checked={fill} onChange={(e) => setFill(e.target.checked)} />
            <span>Заполнить пустые реквизиты фирмы-цели (наименование, ИНН, ОГРН, адрес)</span>
          </label>
          <div className="field-note">
            Периоды и строки отчётности дела заменятся этими {preview.periods.length} годами.
            Амортизация, капитализация, переоценки, нормализация и план продавца переносятся на
            совпадающие годы; обязательства, оценка и процедуры не меняются. Сохраните дело,
            чтобы закрепить загрузку.
          </div>
        </div>
      )}
    </Modal>
  );
}
