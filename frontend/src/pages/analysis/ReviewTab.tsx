import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { httpDetail } from "../../api/client";
import { getProject } from "../../api/projects";
import {
  finalizeBlockReview,
  finalizeProject,
  getReview,
  type Finding,
  type Light,
  type ReviewResponse,
  type Severity,
} from "../../api/review";
import { Button } from "../../components/ui";

const SEV_META: Record<Severity, { label: string; chip: string; color: string }> = {
  risk: { label: "Риск", chip: "status-chip--danger", color: "var(--danger)" },
  warning: { label: "Предупреждение", chip: "status-chip--warn", color: "var(--warn)" },
  info: { label: "Заметка", chip: "status-chip--info", color: "var(--info)" },
};

const LIGHT_META: Record<Light, { title: string; sub: string; color: string }> = {
  ok: { title: "Возражений нет", sub: "Ревью не нашло рисков и предупреждений.", color: "var(--good)" },
  info: { title: "Есть заметки", sub: "Некритичные допущения — стоит перепроверить.", color: "var(--info)" },
  warning: {
    title: "Есть предупреждения",
    sub: "Слабые места плана — рекомендуем усилить перед финализацией.",
    color: "var(--warn)",
  },
  risk: {
    title: "Найдены риски",
    sub: "Существенные риски — требуют осознанного подтверждения до финализации.",
    color: "var(--danger)",
  },
};

const CAT_LABELS: Record<string, string> = {
  viability: "Жизнеспособность",
  liquidity: "Ликвидность",
  structure: "Структура",
  assumptions: "Допущения",
  divergence: "Дивергенция",
};

const fmtEvidence = (v: unknown): string => (Array.isArray(v) ? v.join(", ") : String(v));
const fmtDate = (iso: string) => new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });

function CountPill({ n, label, color }: { n: number; label: string; color: string }) {
  return (
    <div className="rv-count" style={{ opacity: n ? 1 : 0.45 }}>
      <span className="rv-count__n" style={{ color: n ? color : "var(--subtle)" }}>{n}</span>
      <span className="rv-count__l">{label}</span>
    </div>
  );
}

function FindingCard({ f }: { f: Finding }) {
  const meta = SEV_META[f.severity as Severity] ?? SEV_META.info;
  const evidence = Object.entries(f.evidence ?? {});
  return (
    <div className="rv-finding">
      <span className="rv-finding__bar" style={{ background: meta.color }} />
      <div className="rv-finding__body">
        <div className="rv-finding__head">
          <span className={"status-chip " + meta.chip}>{meta.label}</span>
          <span className="rv-finding__cat">{CAT_LABELS[f.category] ?? f.category}</span>
        </div>
        <div className="rv-finding__title">{f.title}</div>
        <div className="rv-finding__detail">{f.detail}</div>
        <div className="rv-finding__rec">
          <span className="rv-finding__arrow">→</span>
          <span>{f.recommendation}</span>
        </div>
        {evidence.length > 0 && (
          <div className="rv-finding__evi">
            {evidence.map(([k, v]) => (
              <span key={k} className="rv-evi-chip">
                {k}: <b>{fmtEvidence(v)}</b>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Гейт финализации (Ф10): risk требует подтверждения; правка модели вернёт в черновик. */
function FinalizeGate({ projectId, review }: { projectId: string; review: ReviewResponse }) {
  const qc = useQueryClient();
  const projectQuery = useQuery({ queryKey: ["project", projectId], queryFn: () => getProject(projectId) });
  const project = projectQuery.data;
  const [ack, setAck] = useState(false);
  const riskCount = review.counts.risk ?? 0;

  const finalize = useMutation({
    mutationFn: () => finalizeProject(projectId, ack),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      qc.invalidateQueries({ queryKey: ["review", projectId] });
    },
  });

  if (project?.status === "finalized") {
    return (
      <div className="rv-final rv-final--done">
        <div className="rv-final__badge">
          <span className="rv-final__check">✓</span>
          <div>
            <div className="rv-final__title">План финализирован</div>
            <div className="rv-final__sub">
              {project.finalized_at ? `Подтверждён ${fmtDate(project.finalized_at)}` : "Подтверждён"}
              {project.finalized_review ? ` · ревью: ${LIGHT_META[project.finalized_review.light as Light]?.title ?? project.finalized_review.light}` : ""}
            </div>
          </div>
        </div>
        {project.finalized_drift && (
          <div className="rv-drift">
            Модель изменилась после финализации — переоцените план и финализируйте заново.
          </div>
        )}
        <div className="rv-final__note">Изменение модели в редакторе вернёт план в черновик.</div>
      </div>
    );
  }

  const blockReview = finalizeBlockReview(finalize.error);
  return (
    <div className="rv-final">
      <div className="rv-final__title">Финализация плана</div>
      <div className="rv-final__sub">
        {riskCount > 0
          ? "План содержит риски. Финализация возможна только с осознанным подтверждением."
          : "Предупреждения и заметки не блокируют — план можно финализировать."}
      </div>
      {riskCount > 0 && (
        <label className="rv-ack">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          <span>Я осознаю перечисленные риски ({riskCount}) и подтверждаю финализацию плана.</span>
        </label>
      )}
      <Button
        className="run-btn"
        loading={finalize.isPending}
        disabled={(riskCount > 0 && !ack) || finalize.isPending}
        onClick={() => finalize.mutate()}
      >
        {finalize.isPending ? "Финализация…" : "Финализировать план"}
      </Button>
      {finalize.isError && (
        <div className="rv-final__err">
          {blockReview
            ? `Гейт не пройден: план содержит ${blockReview.counts.risk ?? 0} риск(ов). Подтвердите осознание.`
            : httpDetail(finalize.error) ?? "Не удалось финализировать. Повторите попытку."}
        </div>
      )}
    </div>
  );
}

/** Вкладка «Ревью плана» (Ф10): «светофор», находки по severity и гейт финализации. */
export function ReviewTab({ projectId }: { projectId: string }) {
  const review = useQuery({
    queryKey: ["review", projectId],
    queryFn: () => getReview(projectId, true), // deep: со стохастикой (divergence)
  });

  return (
    <div>
      <div className="an-head">
        <div style={{ minWidth: 0 }}>
          <div className="an-head__title">Ревью плана</div>
          <div className="an-head__sub">
            Детерминированная проверка модели · находки, рекомендации и гейт финализации.
          </div>
        </div>
        <span className="status-chip status-chip--info">Вне паритета с Project Expert</span>
      </div>

      {review.isPending && (
        <div className="load-card">
          <span className="save-spinner" />
          <div>
            <div className="load-card__title">Прогоняем ревью…</div>
            <div className="load-card__sub">Проверка правил + стохастика (Монте-Карло, чувствительность)</div>
          </div>
        </div>
      )}

      {review.isError && (
        <div className="an-err">
          <div className="an-err__ico">!</div>
          <div style={{ minWidth: 0 }}>
            <div className="an-err__title">Не удалось выполнить ревью</div>
            <div className="an-err__sub">
              {httpDetail(review.error) ?? "Проверьте модель проекта и повторите."}
            </div>
            <Button variant="ghost" onClick={() => review.refetch()}>Повторить</Button>
          </div>
        </div>
      )}

      {review.data && (
        <>
          <div className="rv-light" style={{ borderColor: LIGHT_META[review.data.light as Light]?.color }}>
            <span className="rv-light__dot" style={{ background: LIGHT_META[review.data.light as Light]?.color }} />
            <div className="rv-light__text">
              <div className="rv-light__title">{LIGHT_META[review.data.light as Light]?.title ?? "Ревью"}</div>
              <div className="rv-light__sub">{LIGHT_META[review.data.light as Light]?.sub}</div>
            </div>
            <div className="rv-light__counts">
              <CountPill n={review.data.counts.risk ?? 0} label="рисков" color="var(--danger)" />
              <CountPill n={review.data.counts.warning ?? 0} label="предупр." color="var(--warn)" />
              <CountPill n={review.data.counts.info ?? 0} label="заметок" color="var(--info)" />
            </div>
          </div>

          <FinalizeGate projectId={projectId} review={review.data} />

          {review.data.findings.length === 0 ? (
            <div className="setup-ph">
              <div className="setup-ph__title">Находок нет</div>
              <div className="setup-ph__sub">Ревью не выявило слабых мест — план можно финализировать.</div>
            </div>
          ) : (
            <div className="rv-list">
              {review.data.findings.map((f, i) => (
                <FindingCard key={`${f.id}:${i}`} f={f} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
