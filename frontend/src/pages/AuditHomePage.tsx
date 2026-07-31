import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createAuditSubject, emptyAuditModel, listAuditSubjects } from "../api/audit";
import { IconBriefcase, IconTrash } from "../components/icons";
import { useToast } from "../components/Toast";
import { Button } from "../components/ui";
import { deleteAuditSubject } from "../api/audit";

/**
 * Финанс-Аудит — список субъектов анализа (продукт №2, фаза B).
 * Анализ по фактической отчётности: коэффициенты, тренды, диагностика — фазы C+.
 */
export function AuditHomePage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["audit-subjects"],
    queryFn: listAuditSubjects,
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["audit-subjects"] });

  const create = useMutation({
    mutationFn: () => createAuditSubject("Новый субъект", emptyAuditModel()),
    onSuccess: (s) => navigate(`/audit/${s.id}`),
    onError: () => toast("Не удалось создать субъект", { kind: "error" }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteAuditSubject(id),
    onSuccess: () => { invalidate(); toast("Субъект удалён", { kind: "success" }); },
    onError: () => toast("Не удалось удалить", { kind: "error" }),
  });

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Финанс-Аудит — субъекты анализа</h1>
          <div className="page-sub">
            Анализ финансового состояния предприятия по фактической отчётности.
          </div>
        </div>
        <Button onClick={() => create.mutate()} loading={create.isPending}>
          ＋&nbsp;&nbsp;Субъект
        </Button>
      </div>

      {isLoading ? (
        <div className="page-sub" style={{ padding: 24 }}>Загрузка…</div>
      ) : isError ? (
        <div className="error-state" style={{ padding: "48px 24px" }}>
          <div className="error-state__ico">!</div>
          <div className="error-state__title">Не удалось загрузить субъекты</div>
          <Button variant="ghost" onClick={() => refetch()}>Повторить</Button>
        </div>
      ) : (data ?? []).length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__ico"><IconBriefcase size={30} /></div>
          <div className="tab-empty__title">Пока нет субъектов анализа</div>
          <div className="tab-empty__sub">
            Создайте субъект, введите бухгалтерскую отчётность по периодам (баланс и отчёт о
            финансовых результатах) — далее появятся коэффициенты, тренды и диагностика.
          </div>
          <Button onClick={() => create.mutate()} loading={create.isPending}>
            ＋&nbsp;&nbsp;Создать первый субъект
          </Button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {(data ?? []).map((s) => (
            <div
              key={s.id}
              className="line-card"
              style={{ cursor: "pointer" }}
              onClick={() => navigate(`/audit/${s.id}`)}
            >
              <div className="line-card__head">
                <div className="line-card__idx"><IconBriefcase size={17} /></div>
                <div className="line-card__name" style={{ fontWeight: 700 }}>{s.name}</div>
                <span className="prop-chip">{s.n_periods} периодов</span>
                <span className={"prop-chip " + (s.balanced ? "prop-chip--profit" : "prop-chip--cur")}>
                  {s.balanced ? "Баланс сходится" : "Баланс не сходится"}
                </span>
                <button
                  type="button"
                  className="line-card__del"
                  title="Удалить субъект"
                  onClick={(e) => { e.stopPropagation(); remove.mutate(s.id); }}
                >
                  <IconTrash size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
