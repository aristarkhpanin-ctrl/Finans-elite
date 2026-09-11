import type { AuditRequisites as View, ReportRequisites } from "../api/audit";

/**
 * Реквизиты документа и подписи (SPEC, Прил. Х).
 *
 * Печатный бланк был отчётом о проверке, но не документом сделки: ни адресата, ни
 * номера, ни подписи. Пустые линии под выдуманными должностями печатать было нельзя —
 * и правильный выход не «нарисовать линии», а завести настоящих подписантов.
 *
 * Экран показывает **состояние документа**, а не только поля: подписан он или остаётся
 * рабочим материалом, есть ли опечатка в ИНН, и чего платформа с реквизитами не делает.
 * Опечатка называется, но введённое не выбрасывается: сверить реквизит с реестром
 * платформа не может, и решать человеку.
 */

type Field = [keyof ReportRequisites, string, string];

/** Реквизиты документа: чей это документ и кому он адресован. */
const DOC_FIELDS: Field[] = [
  ["number", "Номер документа", "в делопроизводстве организации"],
  ["addressee", "Адресат", "напр. Инвестиционному комитету ООО «Фонд»"],
];

/** Реквизиты фирмы-цели: то, чем документ её идентифицирует. */
const SUBJECT_FIELDS: Field[] = [
  ["subject_full_name", "Полное наименование", "как в учредительных документах"],
  ["subject_inn", "ИНН", "10 или 12 цифр"],
  ["subject_ogrn", "ОГРН", "13 или 15 цифр"],
  ["subject_address", "Адрес", "юридический адрес"],
];

/** Подписанты: имя обязательно, должность — нет (подписывает человек, а не должность). */
const SIGN_FIELDS: [keyof ReportRequisites, keyof ReportRequisites, string][] = [
  ["executor_name", "executor_role", "Составил"],
  ["approver_name", "approver_role", "Утвердил"],
];

export function AuditRequisites({ value, view, stale = false, onChange }: {
  value: ReportRequisites | undefined;
  /** Состояние документа из разбора: подписан ли, что не так, чего платформа не делает. */
  view: View;
  /**
   * В деле есть несохранённые правки, а состояние ниже посчитано ядром по **сохранённой**
   * модели. Пересчитать его здесь значило бы завести вторую копию правил (подпись без
   * имени, контрольная цифра ИНН) — а две копии расходятся молча. Поэтому отставание не
   * прячется, а называется.
   */
  stale?: boolean;
  onChange: (next: ReportRequisites) => void;
}) {
  const r = value ?? {};
  const upd = (patch: Partial<ReportRequisites>) => onChange({ ...r, ...patch });

  return (
    <div className="audit-block">
      <div className="audit-block__title">Реквизиты документа и подписи</div>
      <div className="page-sub" style={{ marginBottom: 12 }}>
        Заполненное отсюда печатается в заключении и на бланке. Пустой блок ничего не
        ломает: документ выйдет как прежде — и прямо скажет, что он не подписан.
      </div>

      <div className={"req-state " + (view.signed ? "req-state--ok" : "req-state--warn")}>
        {view.signed
          ? `Документ подписан: ${view.signatures.map((s) => s.name).join(", ")}.`
          : "Документ не подписан — на бумаге он выйдет с пометкой «рабочий материал»."}
        {stale && (
          <span className="req-state__stale">
            {" "}Показано по сохранённой версии дела: проверки реквизитов (подпись,
            контрольная цифра ИНН и ОГРН) обновятся после сохранения.
          </span>
        )}
      </div>

      <div className="afields-grid" style={{ marginTop: 12 }}>
        {DOC_FIELDS.map(([key, label, hint]) => (
          <label className="efield" key={key}>
            <span className="efield__label">{label}</span>
            <input className="efield__input" placeholder={hint}
                   value={(r[key] as string) ?? ""}
                   onChange={(e) => upd({ [key]: e.target.value } as Partial<ReportRequisites>)} />
          </label>
        ))}
        <label className="efield">
          <span className="efield__label">Дата документа</span>
          {/* Пустая дата — не ошибка: тогда печатается дата формирования, и так и
              подписана. Выдавать день печати за дату заключения нельзя. */}
          <input className="efield__input" type="date" value={r.date ?? ""}
                 onChange={(e) => upd({ date: e.target.value || null })} />
        </label>
      </div>

      <div className="audit-block__title" style={{ fontSize: 13, marginTop: 16 }}>
        Реквизиты фирмы-цели
      </div>
      <div className="afields-grid">
        {SUBJECT_FIELDS.map(([key, label, hint]) => (
          <label className="efield" key={key}>
            <span className="efield__label">{label}</span>
            <input className="efield__input" placeholder={hint}
                   value={(r[key] as string) ?? ""}
                   onChange={(e) => upd({ [key]: e.target.value } as Partial<ReportRequisites>)} />
          </label>
        ))}
      </div>

      <div className="audit-block__title" style={{ fontSize: 13, marginTop: 16 }}>
        Подписи
      </div>
      <div className="afields-grid">
        {SIGN_FIELDS.map(([nameKey, roleKey, label]) => (
          <div className="req-sign" key={nameKey}>
            <label className="efield">
              <span className="efield__label">{label} — ФИО</span>
              <input className="efield__input" placeholder="И. Петров"
                     value={(r[nameKey] as string) ?? ""}
                     onChange={(e) => upd({ [nameKey]: e.target.value } as Partial<ReportRequisites>)} />
            </label>
            <label className="efield">
              <span className="efield__label">{label} — должность</span>
              <input className="efield__input" placeholder="Аналитик"
                     value={(r[roleKey] as string) ?? ""}
                     onChange={(e) => upd({ [roleKey]: e.target.value } as Partial<ReportRequisites>)} />
            </label>
          </div>
        ))}
      </div>

      {/* Оговорки приходят из ядра и здесь не сочиняются: опечатка в ИНН, должность без
          имени, неподписанный документ — всё названо теми же словами, что на бумаге. */}
      {view.caveats.map((c, i) => (
        <div className="field-note field-note--warn" key={i}>{c}</div>
      ))}

      <div className="page-sub" style={{ marginTop: 12 }}>Чего платформа не делает</div>
      <ul className="sum-gaps">
        {view.not_computed.map((t, i) => <li key={i}>{t}</li>)}
      </ul>
    </div>
  );
}
