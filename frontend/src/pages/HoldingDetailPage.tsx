import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  addHoldingMember,
  consolidateHolding,
  deleteHolding,
  getHolding,
  HOLDING_ROLES,
  patchHoldingMember,
  removeHoldingMember,
  type ConsolidateResponse,
} from "../api/holdings";
import { listProjects } from "../api/projects";
import { EPercentField, ESelect } from "../components/EditorField";
import { IconTrash } from "../components/icons";
import { useToast } from "../components/Toast";
import { Button, ErrorState, Loading, Modal } from "../components/ui";
import { fmtMillions, fmtTable, percent } from "../format";

const roleColor = (r: string) => (r === "parent" ? "var(--primary)" : "var(--info)");

export function HoldingDetailPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const [addOpen, setAddOpen] = useState(false);
  const [pickProject, setPickProject] = useState("");
  const [pickRole, setPickRole] = useState("subsidiary");
  const [groupRate, setGroupRate] = useState("0.15");
  const [result, setResult] = useState<ConsolidateResponse | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const holdingQuery = useQuery({ queryKey: ["holding", id], queryFn: () => getHolding(id) });
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: listProjects });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["holding", id] });
    qc.invalidateQueries({ queryKey: ["holdings"] });
  };

  const add = useMutation({
    mutationFn: () => addHoldingMember(id, pickProject, pickRole),
    onSuccess: () => {
      setAddOpen(false);
      setPickProject("");
      setResult(null);
      invalidate();
    },
    onError: () => toast("Не удалось добавить проект", { kind: "error" }),
  });
  const patchRole = useMutation({
    mutationFn: ({ pid, role }: { pid: string; role: string }) => patchHoldingMember(id, pid, role),
    onSuccess: () => {
      setResult(null);
      invalidate();
    },
  });
  const removeM = useMutation({
    mutationFn: (pid: string) => removeHoldingMember(id, pid),
    onSuccess: () => {
      setResult(null);
      invalidate();
    },
  });
  const consolidate = useMutation({
    mutationFn: () => consolidateHolding(id, groupRate),
    onSuccess: (data) => {
      setResult(data);
      invalidate();
    },
    onError: () => toast("Не удалось консолидировать", { kind: "error" }),
  });
  const removeHolding = useMutation({
    mutationFn: () => deleteHolding(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["holdings"] });
      navigate("/holdings");
    },
  });

  if (holdingQuery.isError) return <ErrorState text="Не удалось загрузить холдинг." />;
  if (holdingQuery.isLoading || !holdingQuery.data) return <Loading />;

  const holding = holdingQuery.data;
  const projects = projectsQuery.data ?? [];
  const projectName = (pid: string) => projects.find((p) => p.id === pid)?.name ?? pid;
  const memberIds = new Set(holding.members.map((m) => m.project_id));
  const available = projects.filter((p) => !memberIds.has(p.id));
  const parents = holding.members.filter((m) => m.role === "parent").length;

  const openAdd = () => {
    setPickProject(available[0]?.id ?? "");
    setPickRole("subsidiary");
    setAddOpen(true);
  };

  return (
    <div>
      <div className="crumbs" style={{ marginBottom: 12 }}>
        <Link to="/holdings">Холдинги</Link>
        <span className="crumbs__sep">›</span>
        <span className="crumbs__active">{holding.name}</span>
      </div>

      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title">{holding.name}</h1>
          <div className="page-sub">
            {holding.members.length} {holding.members.length === 1 ? "проект" : "проектов"} ·{" "}
            {parents > 0 ? "головной + дочерние" : "структура не задана"}
          </div>
        </div>
        <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
          Удалить холдинг
        </Button>
      </div>

      {/* Состав холдинга */}
      <div className="terms-head" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span>Состав холдинга</span>
        {available.length > 0 && (
          <Button variant="ghost" onClick={openAdd}>
            ＋&nbsp;&nbsp;Добавить проект
          </Button>
        )}
      </div>

      {holding.members.length === 0 ? (
        <div className="tab-empty" style={{ padding: "40px 24px" }}>
          <div className="tab-empty__title">В холдинге пока нет проектов</div>
          <div className="tab-empty__sub">
            Добавьте проекты, назначьте головной и дочерние — и постройте сводный бюджет.
          </div>
          {available.length > 0 ? (
            <Button onClick={openAdd}>＋&nbsp;&nbsp;Добавить проект</Button>
          ) : (
            <p className="muted">Сначала создайте проекты в организации.</p>
          )}
        </div>
      ) : (
        <div className="member-list">
          {holding.members.map((m) => {
            const perNpv = result?.per_project.find((p) => p.project_id === m.project_id)?.npv;
            return (
              <div className="member-row" key={m.project_id}>
                <span className="member-role-dot" style={{ background: roleColor(m.role) }} />
                <span className="member-name">{projectName(m.project_id)}</span>
                <span
                  className="member-npv"
                  style={{ color: perNpv && Number(perNpv) < 0 ? "var(--danger)" : "var(--muted)" }}
                >
                  {perNpv !== undefined ? fmtMillions(perNpv, { digits: 1 }) : "—"}
                </span>
                <div className="member-role-sel">
                  <ESelect
                    label=""
                    value={m.role}
                    onChange={(role) => patchRole.mutate({ pid: m.project_id, role })}
                    options={HOLDING_ROLES}
                  />
                </div>
                <button
                  type="button"
                  className="icon-action icon-action--danger"
                  title="Исключить из холдинга"
                  onClick={() => removeM.mutate(m.project_id)}
                >
                  <IconTrash size={15} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Консолидация */}
      <div className="section-card" style={{ marginTop: 20 }}>
        <div className="section-card__head">
          <span className="section-card__title" style={{ margin: 0 }}>
            Консолидация
          </span>
        </div>
        <div style={{ display: "flex", gap: 14, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ width: 200 }}>
            <EPercentField
              label="Ставка группы"
              suffix="% / год"
              hint="Ставка дисконтирования для сводного NPV группы"
              value={groupRate}
              onChange={setGroupRate}
            />
          </div>
          <Button
            loading={consolidate.isPending}
            disabled={holding.members.length === 0}
            onClick={() => consolidate.mutate()}
          >
            {consolidate.isPending ? "Консолидация…" : "Консолидировать →"}
          </Button>
          <span className="page-sub" style={{ flex: 1, minWidth: 180 }}>
            Построчная сумма отчётов всех участников и групповые показатели.
          </span>
        </div>
      </div>

      {result && <ConsolidatedBudget result={result} rate={groupRate} />}

      {/* Модал добавления проекта */}
      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Добавить проект в холдинг"
        maxWidth={440}
        actions={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              Отмена
            </Button>
            <Button loading={add.isPending} disabled={!pickProject} onClick={() => add.mutate()}>
              Добавить
            </Button>
          </>
        }
      >
        {available.length === 0 ? (
          <p className="muted">Все проекты организации уже в холдинге.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <ESelect
              label="Проект"
              value={pickProject}
              onChange={setPickProject}
              options={available.map((p) => [p.id, p.name] as [string, string])}
            />
            <ESelect label="Роль в холдинге" value={pickRole} onChange={setPickRole} options={HOLDING_ROLES} />
          </div>
        )}
      </Modal>

      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} maxWidth={420}>
        <div style={{ textAlign: "center" }}>
          <div className="modal-danger-ico">
            <IconTrash size={22} />
          </div>
          <h3 className="modal__title">Удалить холдинг?</h3>
          <div className="modal__sub">
            Группировка «<b style={{ color: "var(--text)" }}>{holding.name}</b>» будет удалена.
            Проекты останутся в организации.
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <Button variant="ghost" style={{ flex: 1 }} onClick={() => setConfirmDelete(false)}>
              Отмена
            </Button>
            <Button variant="danger" style={{ flex: 1 }} loading={removeHolding.isPending} onClick={() => removeHolding.mutate()}>
              Удалить
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

/** Сводный бюджет: мета-чипы, 4 метрики, таблица вклада проектов. */
function ConsolidatedBudget({ result, rate }: { result: ConsolidateResponse; rate: string }) {
  const m = result.metrics;
  const per = result.per_project;
  const sum = (key: "revenue_total" | "net_profit_total") =>
    per.reduce((s, p) => s + Number(p[key]), 0);

  const rows: Array<{ label: string; get: (p: (typeof per)[0]) => string; total: string; neg?: (v: number) => boolean }> = [
    { label: "Выручка", get: (p) => fmtTable(p.revenue_total).text, total: fmtTable(sum("revenue_total")).text },
    {
      label: "Чистая прибыль",
      get: (p) => fmtTable(p.net_profit_total).text,
      total: fmtTable(sum("net_profit_total")).text,
      neg: (v) => v < 0,
    },
    { label: "NPV", get: (p) => fmtMillions(p.npv, { digits: 1 }), total: fmtMillions(m.npv, { digits: 1 }), neg: (v) => v < 0 },
    { label: "IRR", get: (p) => (p.irr_annual ? percent(p.irr_annual, 1) : "—"), total: m.irr_annual ? percent(m.irr_annual, 1) : "—" },
  ];

  return (
    <div style={{ marginTop: 20 }}>
      <div className="terms-head">Сводный бюджет</div>
      <div className="consol-meta">
        <span className="consol-chip">
          ставка группы <b>{percent(rate, 1)}</b>
        </span>
        <span className="consol-chip">
          движок <b>{result.engine_version}</b>
        </span>
        <span className="consol-chip">
          проектов <b>{per.length}</b>
        </span>
      </div>

      <div className="metrics">
        <div className="metric">
          <div className="m-label">Сводный NPV</div>
          <div className="m-value" style={{ color: Number(m.npv) < 0 ? "var(--danger)" : undefined }}>
            {fmtMillions(m.npv, { sign: true, digits: 1 })}
          </div>
        </div>
        <div className="metric">
          <div className="m-label">Групповой IRR</div>
          <div className="m-value">{m.irr_annual ? percent(m.irr_annual, 1) : "—"}</div>
        </div>
        <div className="metric">
          <div className="m-label">Выручка группы</div>
          <div className="m-value">{fmtMillions(String(sum("revenue_total")), { digits: 1 })}</div>
        </div>
        <div className="metric">
          <div className="m-label">Чистая прибыль</div>
          <div className="m-value" style={{ color: sum("net_profit_total") < 0 ? "var(--danger)" : undefined }}>
            {fmtMillions(String(sum("net_profit_total")), { sign: true, digits: 1 })}
          </div>
        </div>
      </div>

      {/* Таблица вклада: показатель | проекты | группа */}
      <div className="terms-head" style={{ marginTop: 18 }}>
        Вклад проектов
      </div>
      <div className="contrib-wrap fe-scroll">
        <div className="contrib-row contrib-row--head">
          <div className="contrib-label">Показатель</div>
          {per.map((p) => (
            <div key={p.project_id} className="contrib-cell" title={p.name}>
              <span className="member-role-dot" style={{ background: roleColor(p.role) }} />
              {p.name.length > 14 ? p.name.slice(0, 13) + "…" : p.name}
            </div>
          ))}
          <div className="contrib-cell">Группа</div>
        </div>
        {rows.map((r) => (
          <div key={r.label} className={"contrib-row" + (r.label === "NPV" ? " contrib-row--total" : "")}>
            <div className="contrib-label">{r.label}</div>
            {per.map((p) => (
              <div
                key={p.project_id}
                className={"contrib-cell" + (r.neg && r.neg(Number(p[r.label === "Выручка" ? "revenue_total" : r.label === "Чистая прибыль" ? "net_profit_total" : "npv"])) ? " contrib-cell--neg" : "")}
              >
                {r.get(p)}
              </div>
            ))}
            <div className="contrib-cell" style={{ fontWeight: 700 }}>
              {r.total}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
