import type { ProjectModel } from "../api/model";
import { validateModel } from "../validation";

/** Панель замечаний по модели (ошибки/предупреждения ввода). */
export function ValidationPanel({ model }: { model: ProjectModel }) {
  const issues = validateModel(model);
  if (issues.length === 0) return null;
  return (
    <div className="validation">
      {issues.map((it, i) => (
        <div key={i} className={`validation-item validation-item--${it.severity}`}>
          <span className="validation-icon">{it.severity === "error" ? "⚠" : "ⓘ"}</span>
          <span>{it.message}</span>
        </div>
      ))}
    </div>
  );
}
