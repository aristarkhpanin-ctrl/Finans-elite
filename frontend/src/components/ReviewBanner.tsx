import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getReview, type Light } from "../api/review";

const LIGHT: Record<Light, { title: string; color: string }> = {
  ok: { title: "Ревью: возражений нет", color: "var(--good)" },
  info: { title: "Ревью: есть заметки", color: "var(--info)" },
  warning: { title: "Ревью: есть предупреждения", color: "var(--warn)" },
  risk: { title: "Ревью: найдены риски", color: "var(--danger)" },
};

/** Компактный «светофор» ревью на странице результатов со ссылкой на полную вкладку. */
export function ReviewBanner({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const review = useQuery({
    queryKey: ["review-fast", projectId],
    queryFn: () => getReview(projectId, false), // быстрое ревью (без стохастики divergence)
    retry: false,
  });
  const data = review.data;
  if (!data) return null; // не мешаем странице во время загрузки/ошибки ревью

  const light = (LIGHT[data.light as Light] ? data.light : "info") as Light;
  const meta = LIGHT[light];
  const c = data.counts;
  const top = data.findings[0];

  return (
    <button
      type="button"
      className="rv-banner"
      style={{ borderLeftColor: meta.color }}
      onClick={() => navigate(`/projects/${projectId}/analysis`)}
    >
      <span className="rv-banner__dot" style={{ background: meta.color }} />
      <div className="rv-banner__text">
        <div className="rv-banner__title">{meta.title}</div>
        <div className="rv-banner__sub">{top ? top.title : "План не вызывает возражений."}</div>
      </div>
      <div className="rv-banner__counts">
        {(c.risk ?? 0) > 0 && <span className="rv-bchip rv-bchip--risk">{c.risk} риск.</span>}
        {(c.warning ?? 0) > 0 && <span className="rv-bchip rv-bchip--warn">{c.warning} предупр.</span>}
        {(c.info ?? 0) > 0 && <span className="rv-bchip rv-bchip--info">{c.info} замет.</span>}
      </div>
      <span className="rv-banner__arrow">Разбор&nbsp;→</span>
    </button>
  );
}
