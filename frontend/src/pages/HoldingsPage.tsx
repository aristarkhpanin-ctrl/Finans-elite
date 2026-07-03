import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createHolding, deleteHolding, listHoldings } from "../api/holdings";
import { CubeHero } from "../components/CubeHero";
import { IconTrash } from "../components/icons";
import { useToast } from "../components/Toast";
import { Button, Modal, Skeleton } from "../components/ui";
import { fmtMillions } from "../format";

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

export function HoldingsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const [name, setName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["holdings"], queryFn: listHoldings });

  const create = useMutation({
    mutationFn: () => createHolding(name.trim()),
    onSuccess: (h) => {
      setName("");
      qc.invalidateQueries({ queryKey: ["holdings"] });
      navigate(`/holdings/${h.id}`);
    },
    onError: () => toast("Не удалось создать холдинг (нужны права)", { kind: "error" }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteHolding(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["holdings"] });
      setDeleteTarget(null);
      toast("Холдинг удалён", { kind: "success" });
    },
    onError: () => toast("Не удалось удалить холдинг", { kind: "error" }),
  });

  const list = data ?? [];
  const empty = !!data && list.length === 0;

  const createCard = (
    <div className="create-card">
      <div className="create-card__row">
        <div style={{ flex: 1, minWidth: 0 }}>
          <label className="auth-label" style={{ display: "block", marginBottom: 7 }}>
            Название холдинга
          </label>
          <input
            className="input"
            style={{ width: "100%" }}
            placeholder="Напр. «Группа «Вертикаль»"
            value={name}
            disabled={create.isPending}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && name.trim() && !create.isPending && create.mutate()}
          />
        </div>
        <Button className="create-card__btn" loading={create.isPending} disabled={!name.trim()} onClick={() => create.mutate()}>
          {create.isPending ? "Создаём…" : "Создать холдинг"}
        </Button>
      </div>
    </div>
  );

  return (
    <div>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title">Холдинги</h1>
          <div className="page-sub">Группы проектов с консолидированной отчётностью.</div>
        </div>
        {list.length > 0 && (
          <span className="count-pill">
            {list.length} {plural(list.length, "холдинг", "холдинга", "холдингов")}
          </span>
        )}
      </div>

      {isLoading && (
        <>
          <Skeleton height={120} style={{ borderRadius: 16, marginBottom: 30 }} />
          <div className="proj-grid">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} height={150} style={{ borderRadius: 14 }} />
            ))}
          </div>
        </>
      )}

      {isError && (
        <div className="error-state" style={{ padding: "48px 24px" }}>
          <div className="error-state__ico">!</div>
          <div className="error-state__title">Не удалось загрузить холдинги</div>
          <Button onClick={() => refetch()}>↻&nbsp;&nbsp;Повторить</Button>
        </div>
      )}

      {data && (
        <>
          {empty && (
            <div className="onboard">
              <div className="onboard__ico">
                <div style={{ width: 46, height: 46 }}>
                  <CubeHero backdrop="transparent" showEnvironment={false} showOrbit={false} pointerTilt={false} />
                </div>
              </div>
              <div className="onboard__title">Создайте первый холдинг</div>
              <div className="onboard__sub">
                Объедините проекты в группу и получите консолидированный бюджет — сводные отчёты и
                показатели по всем участникам сразу.
              </div>
            </div>
          )}

          {createCard}

          {!empty && (
            <div className="proj-grid">
              {list.map((h) => {
                const consolidated = h.last_consolidation;
                return (
                  <div key={h.id} className="proj-card">
                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
                      <button type="button" className="proj-card__name" onClick={() => navigate(`/holdings/${h.id}`)}>
                        {h.name}
                      </button>
                      <span className={"status-chip" + (consolidated ? "" : " status-chip--warn")}>
                        {consolidated ? "● Консолидирован" : "○ Не консолидирован"}
                      </span>
                    </div>
                    <div className="proj-card__metrics">
                      <div style={{ flex: 1 }}>
                        <div className="mini-label">Проектов</div>
                        <div className="proj-card__val">{h.members.length}</div>
                      </div>
                      <div style={{ flex: 1 }}>
                        <div className="mini-label">Сводный NPV</div>
                        <div className={"proj-card__val" + (consolidated && Number(consolidated.npv) < 0 ? " proj-card__val--neg" : consolidated ? "" : " proj-card__val--none")}>
                          {consolidated ? fmtMillions(consolidated.npv, { digits: 1 }) : "—"}
                        </div>
                      </div>
                    </div>
                    <div className="proj-card__foot">
                      <button type="button" className="proj-card__name" style={{ fontSize: 12, color: "var(--accent)" }} onClick={() => navigate(`/holdings/${h.id}`)}>
                        Открыть →
                      </button>
                      <button
                        type="button"
                        className="icon-action icon-action--danger"
                        title="Удалить холдинг"
                        onClick={() => setDeleteTarget({ id: h.id, name: h.name })}
                      >
                        <IconTrash size={15} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      <Modal open={!!deleteTarget} onClose={() => !remove.isPending && setDeleteTarget(null)} maxWidth={420}>
        <div style={{ textAlign: "center" }}>
          <div className="modal-danger-ico">
            <IconTrash size={22} />
          </div>
          <h3 className="modal__title">Удалить холдинг?</h3>
          <div className="modal__sub">
            Холдинг «<b style={{ color: "var(--text)" }}>{deleteTarget?.name}</b>» будет удалён.
            Входящие в него проекты останутся — удалится только группировка.
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <Button variant="ghost" style={{ flex: 1 }} disabled={remove.isPending} onClick={() => setDeleteTarget(null)}>
              Отмена
            </Button>
            <Button variant="danger" style={{ flex: 1 }} loading={remove.isPending} onClick={() => deleteTarget && remove.mutate(deleteTarget.id)}>
              Удалить холдинг
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
