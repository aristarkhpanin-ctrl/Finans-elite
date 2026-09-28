import type { AuditInputIssue } from "../api/audit";

/**
 * Панель качества ввода (макет «Финанс Аудит — Экран 19, Ошибки данных»).
 *
 * Отделена от оговорок анализа намеренно. Оговорка говорит о результате («числа
 * посчитаны с учётом переоценки»), находка — о самих данных («актив не равен пассиву
 * в 2024 на −849»). Смешать их в один список значило бы поставить рядом «имейте в
 * виду» и «это надо исправить», а действовать пользователь должен по-разному.
 *
 * Находка всегда несёт периоды и числа: сообщение без величины заставляет искать
 * проблему руками, а искать её должен инструмент.
 */

const SEVERITY: Record<AuditInputIssue["severity"], { label: string; cls: string }> = {
  error: { label: "Ошибка", cls: "issue--error" },
  warning: { label: "Внимание", cls: "issue--warn" },
  info: { label: "Замечание", cls: "issue--info" },
};

/** Заголовок панели: сколько находок и какого веса. */
function headline(issues: AuditInputIssue[]): string {
  const n = (s: string) => issues.filter((i) => i.severity === s).length;
  return [n("error") && `${n("error")} ошибок в данных`,
          n("warning") && `${n("warning")} предупреждений`,
          n("info") && `${n("info")} замечаний`]
    .filter(Boolean).join(" · ");
}

export function AuditInputIssues({
  issues,
  periods,
}: {
  issues: AuditInputIssue[];
  /** Подписи периодов — чтобы находка называла период так же, как таблицы. */
  periods: string[];
}) {
  // Чистый ввод — не повод для панели «всё хорошо»: пустое место говорит то же самое,
  // но не занимает внимание, которого на экране с числами и так мало.
  if (issues.length === 0) return null;

  return (
    <div className="audit-block" data-testid="input-issues">
      <div className="audit-block__title">Качество данных</div>
      <div className="page-sub" style={{ marginBottom: 12 }}>{headline(issues)}</div>

      <div className="issue-list">
        {issues.map((issue, i) => (
          <div className={"issue " + SEVERITY[issue.severity].cls} key={issue.code + i}>
            <div className="issue__head">
              <span className="issue__badge">{SEVERITY[issue.severity].label}</span>
              <span className="issue__title">{issue.title}</span>
              {issue.periods.length > 0 && (
                <span className="issue__periods">
                  {issue.periods.map((t) => periods[t] ?? `Период ${t + 1}`).join(", ")}
                </span>
              )}
            </div>
            <div className="issue__detail">{issue.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
