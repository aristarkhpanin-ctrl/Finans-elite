import { useState } from "react";
import type { ProjectModel } from "../api/model";
import { validateModel } from "../validation";

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

/**
 * Панель замечаний по модели (макет «Этап 5»): свёрнутая строка с точкой-статусом,
 * суммарным текстом и счётчиками err/warn ↔ развёрнутый список с тегами «где».
 */
export function ValidationPanel({ model }: { model: ProjectModel }) {
  const [open, setOpen] = useState(true);
  const issues = validateModel(model);
  const errCount = issues.filter((i) => i.severity === "error").length;
  const warnCount = issues.length - errCount;
  const clean = issues.length === 0;

  const summary = clean
    ? "Замечаний нет — модель готова к расчёту"
    : errCount
      ? `${errCount} ${plural(errCount, "ошибка", "ошибки", "ошибок")}` +
        (warnCount ? `, ${warnCount} предупр.` : "")
      : `${warnCount} ${plural(warnCount, "предупреждение", "предупреждения", "предупреждений")}`;

  const cls = "val-panel" + (clean ? "" : errCount ? " val-panel--err" : " val-panel--warn");

  return (
    <div className={cls}>
      <button type="button" className="val-panel__head" onClick={() => setOpen((v) => !v)}>
        <span className="val-panel__dot" />
        <span className="val-panel__text">{summary}</span>
        {errCount > 0 && <span className="val-count val-count--err">{errCount}</span>}
        {warnCount > 0 && <span className="val-count val-count--warn">{warnCount}</span>}
        <span style={{ flex: 1 }} />
        {!clean && <span className="val-panel__chev">{open ? "▲" : "▼"}</span>}
      </button>
      {open && !clean && (
        <div className="val-panel__body">
          {issues.map((it, i) => (
            <div key={i} className={`val-item val-item--${it.severity}`}>
              <span className="val-item__ico">{it.severity === "error" ? "!" : "△"}</span>
              <span className="val-item__text">{it.message}</span>
              <span className="val-item__tag">{it.where}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
