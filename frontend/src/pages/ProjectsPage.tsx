import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createProject,
  createProjectFromTemplate,
  deleteProject,
  duplicateProject,
  listProjects,
  listTemplates,
} from "../api/projects";
import type { ProjectSummary } from "../api/types";
import { CubeHero } from "../components/CubeHero";
import {
  IconBriefcase,
  IconBuilding,
  IconCart,
  IconCopy,
  IconFactory,
  IconSearch,
  IconTrash,
} from "../components/icons";
import { useToast } from "../components/Toast";
import { Button, Modal, Skeleton } from "../components/ui";
import { fmtMillions, percent } from "../format";

/** Вид списка (localStorage). */
const VIEW_KEY = "fe_projects_view";
type View = "cards" | "rows";

/** Иконка/бейдж карточки шаблона по id бэкенда. */
const TPL_META: Record<string, { n: 1 | 2 | 3 | 4; icon: JSX.Element; badge?: string }> = {
  production: { n: 1, icon: <IconFactory size={20} />, badge: "демо" },
  trade: { n: 2, icon: <IconCart size={20} /> },
  services: { n: 3, icon: <IconBriefcase size={20} /> },
  enterprise: { n: 4, icon: <IconBuilding size={20} /> },
};

const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

type Status = { text: string; dot: string; cls: string };

function statusOf(p: ProjectSummary): Status {
  if (!p.last_calc) return { text: "Черновик", dot: "○", cls: "status-chip status-chip--warn" };
  if (p.is_stale) return { text: "Изменён", dot: "●", cls: "status-chip status-chip--info" };
  return { text: "Рассчитан", dot: "●", cls: "status-chip" };
}

function npvCls(p: ProjectSummary): string {
  if (!p.last_calc) return "proj-card__val proj-card__val--none";
  return Number(p.last_calc.npv) < 0 ? "proj-card__val proj-card__val--neg" : "proj-card__val";
}

function paybackText(p: ProjectSummary): string {
  if (!p.last_calc) return "—";
  return p.last_calc.pb_months !== null ? `${p.last_calc.pb_months} мес` : "> горизонта";
}

function dateText(p: ProjectSummary): string {
  return p.updated_at === p.created_at
    ? `создан ${fmtDate(p.created_at)}`
    : `изм. ${fmtDate(p.updated_at)}`;
}

export function ProjectsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");
  const [view, setView] = useState<View>(() => (localStorage.getItem(VIEW_KEY) as View) || "cards");
  const [creatingTpl, setCreatingTpl] = useState<string | null>(null);
  const [created, setCreated] = useState<{ id: string; name: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const { data: templates } = useQuery({ queryKey: ["templates"], queryFn: listTemplates });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["projects"] });

  const create = useMutation({
    mutationFn: () => createProject(name.trim() || "Новый проект"),
    onSuccess: (p) => {
      setName("");
      invalidate();
      setCreated({ id: p.id, name: p.name });
    },
    onError: () => toast("Не удалось создать проект", { kind: "error" }),
  });

  const fromTemplate = useMutation({
    mutationFn: (tpl: { id: string; name: string }) =>
      createProjectFromTemplate(tpl.id, name.trim() || tpl.name),
    onMutate: (tpl) => setCreatingTpl(tpl.id),
    onSettled: () => setCreatingTpl(null),
    onSuccess: (p) => {
      setName("");
      invalidate();
      setCreated({ id: p.id, name: p.name });
    },
    onError: () => toast("Не удалось создать проект из шаблона", { kind: "error" }),
  });

  const duplicate = useMutation({
    mutationFn: (id: string) => duplicateProject(id),
    onSuccess: (p) => {
      invalidate();
      toast("Копия создана", { kind: "success", sub: p.name });
    },
    onError: () => toast("Не удалось создать копию", { kind: "error" }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
      invalidate();
      setDeleteTarget(null);
      toast("Проект удалён", { kind: "success" });
    },
    onError: () => toast("Не удалось удалить проект", { kind: "error" }),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    return q ? data.filter((p) => p.name.toLowerCase().includes(q)) : data;
  }, [data, search]);

  const empty = !!data && data.length === 0;

  function setViewPersist(v: View) {
    setView(v);
    localStorage.setItem(VIEW_KEY, v);
  }

  const actionButtons = (p: ProjectSummary) => (
    <>
      <button
        type="button"
        className="icon-action"
        title="Дублировать"
        disabled={duplicate.isPending}
        onClick={() => duplicate.mutate(p.id)}
      >
        <IconCopy size={15} />
      </button>
      <button
        type="button"
        className="icon-action icon-action--danger"
        title="Удалить"
        onClick={() => setDeleteTarget({ id: p.id, name: p.name })}
      >
        <IconTrash size={15} />
      </button>
    </>
  );

  return (
    <div>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title">Проекты</h1>
          <div className="page-sub">Финансовые модели и инвестпроекты вашей организации</div>
        </div>
        {data && data.length > 0 && (
          <span className="count-pill">
            {data.length} {plural(data.length, "проект", "проекта", "проектов")}
          </span>
        )}
      </div>

      {isLoading && (
        <>
          <Skeleton height={120} style={{ borderRadius: 16, marginBottom: 30 }} />
          <div className="tpl-grid" style={{ marginBottom: 30 }}>
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} height={150} style={{ borderRadius: 13 }} />
            ))}
          </div>
          <Skeleton width={180} height={22} style={{ margin: "8px 0 16px" }} />
          <div className="proj-grid">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} height={170} style={{ borderRadius: 14 }} />
            ))}
          </div>
        </>
      )}

      {isError && (
        <div className="error-state" style={{ padding: "56px 24px" }}>
          <div className="error-state__ico">!</div>
          <div className="error-state__title">Не удалось загрузить проекты</div>
          <div className="page-sub" style={{ maxWidth: 380, textAlign: "center" }}>
            Проверьте соединение и попробуйте снова. Если ошибка повторяется — обратитесь в поддержку.
          </div>
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
              <div className="onboard__title">Создайте первый проект</div>
              <div className="onboard__sub">
                Начните с пустой модели или выберите готовый шаблон ниже — он заполнит структуру за
                вас, останется ввести цифры.
              </div>
            </div>
          )}

          <div className="create-card">
            <div className="create-card__row">
              <div style={{ flex: 1, minWidth: 0 }}>
                <label className="auth-label" style={{ display: "block", marginBottom: 7 }}>
                  Название нового проекта
                </label>
                <input
                  className="input"
                  style={{ width: "100%" }}
                  placeholder="Напр. «Завод полимерной упаковки»"
                  value={name}
                  disabled={create.isPending || fromTemplate.isPending}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !create.isPending && create.mutate()}
                />
              </div>
              <Button className="create-card__btn" loading={create.isPending} onClick={() => create.mutate()}>
                {create.isPending ? "Создаём…" : "Создать пустой"}
              </Button>
            </div>

            {templates && templates.length > 0 && (
              <>
                <div className="tpl-label">Или начните с шаблона</div>
                <div className="tpl-grid">
                  {templates.map((tpl) => {
                    const meta = TPL_META[tpl.id] ?? { n: 2 as const, icon: <IconBriefcase size={20} /> };
                    const busy = creatingTpl === tpl.id;
                    return (
                      <button
                        key={tpl.id}
                        type="button"
                        className="tpl-card"
                        disabled={fromTemplate.isPending || create.isPending}
                        onClick={() => fromTemplate.mutate({ id: tpl.id, name: tpl.name })}
                      >
                        <div className="tpl-card__top">
                          <div className={`tpl-card__ico tpl-card__ico--${meta.n}`}>{meta.icon}</div>
                          {meta.badge && <span className="tpl-badge">{meta.badge}</span>}
                        </div>
                        <div className="tpl-card__name">{tpl.name}</div>
                        <div className="tpl-card__desc">{tpl.description}</div>
                        <div className="tpl-card__foot">
                          {busy ? (
                            <>
                              <span className="btn__spinner" style={{ color: "var(--accent)" }} />
                              <span className="tpl-card__use">Создаём…</span>
                            </>
                          ) : (
                            <span className="tpl-card__use">Использовать →</span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>

          {!empty && (
            <>
              <div className="list-head">
                <div className="list-head__title">Ваши проекты</div>
                <div className="list-tools">
                  <div className="search-box">
                    <IconSearch size={15} />
                    <input
                      placeholder="Поиск проекта"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                  <div className="view-toggle">
                    <button
                      type="button"
                      title="Карточки"
                      className={"view-toggle__btn" + (view === "cards" ? " view-toggle__btn--active" : "")}
                      onClick={() => setViewPersist("cards")}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                        <rect x="3" y="3" width="8" height="8" rx="1.5" />
                        <rect x="13" y="3" width="8" height="8" rx="1.5" />
                        <rect x="3" y="13" width="8" height="8" rx="1.5" />
                        <rect x="13" y="13" width="8" height="8" rx="1.5" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      title="Список"
                      className={"view-toggle__btn" + (view === "rows" ? " view-toggle__btn--active" : "")}
                      onClick={() => setViewPersist("rows")}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                        <rect x="3" y="4" width="18" height="3" rx="1.5" />
                        <rect x="3" y="10.5" width="18" height="3" rx="1.5" />
                        <rect x="3" y="17" width="18" height="3" rx="1.5" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>

              {filtered.length === 0 ? (
                <p className="muted" style={{ textAlign: "center", padding: "24px 0" }}>
                  Ничего не найдено по запросу «{search.trim()}»
                </p>
              ) : view === "cards" ? (
                <div className="proj-grid">
                  {filtered.map((p, i) => {
                    const st = statusOf(p);
                    return (
                      <div key={p.id} className="proj-card" style={{ animationDelay: `${i * 0.03}s` }}>
                        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
                          <button type="button" className="proj-card__name" onClick={() => navigate(`/projects/${p.id}`)}>
                            {p.name}
                          </button>
                          <span className={st.cls}>
                            {st.dot} {st.text}
                          </span>
                        </div>
                        <div className="proj-card__metrics">
                          <div style={{ flex: 1 }}>
                            <div className="mini-label">NPV</div>
                            <div className={npvCls(p)}>
                              {p.last_calc ? fmtMillions(p.last_calc.npv, { digits: 2 }) : "—"}
                            </div>
                          </div>
                          <div style={{ flex: 1 }}>
                            <div className="mini-label">IRR</div>
                            <div className="proj-card__val">
                              {p.last_calc?.irr_annual ? percent(p.last_calc.irr_annual, 1) : "—"}
                            </div>
                          </div>
                          <div style={{ flex: 1 }}>
                            <div className="mini-label">Окуп.</div>
                            <div className="proj-card__val proj-card__val--dim">{paybackText(p)}</div>
                          </div>
                        </div>
                        <div className="proj-card__foot">
                          <span className="proj-card__date">{dateText(p)}</span>
                          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>{actionButtons(p)}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="proj-table">
                  <div className="proj-table__head">
                    <div className="proj-col-name">Проект</div>
                    <div className="proj-col-status">Статус</div>
                    <div className="proj-col-num">NPV</div>
                    <div className="proj-col-num">IRR</div>
                    <div className="proj-col-date">Изменён</div>
                    <div className="proj-col-act" />
                  </div>
                  {filtered.map((p) => {
                    const st = statusOf(p);
                    return (
                      <div key={p.id} className="proj-row">
                        <div className="proj-col-name">
                          <button type="button" className="proj-row__link" onClick={() => navigate(`/projects/${p.id}`)}>
                            {p.name}
                          </button>
                        </div>
                        <div className="proj-col-status">
                          <span className={st.cls}>
                            {st.dot} {st.text}
                          </span>
                        </div>
                        <div
                          className="proj-col-num"
                          style={{
                            color: !p.last_calc
                              ? "var(--subtle)"
                              : Number(p.last_calc.npv) < 0
                                ? "var(--danger)"
                                : "var(--text)",
                          }}
                        >
                          {p.last_calc ? fmtMillions(p.last_calc.npv, { digits: 2 }) : "—"}
                        </div>
                        <div className="proj-col-num" style={{ color: "var(--muted)" }}>
                          {p.last_calc?.irr_annual ? percent(p.last_calc.irr_annual, 1) : "—"}
                        </div>
                        <div className="proj-col-date">{dateText(p)}</div>
                        <div className="proj-col-act">{actionButtons(p)}</div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </>
      )}

      <Modal
        open={!!deleteTarget}
        onClose={() => !remove.isPending && setDeleteTarget(null)}
        maxWidth={420}
      >
        <div style={{ textAlign: "center" }}>
          <div className="modal-danger-ico">
            <IconTrash size={22} />
          </div>
          <h3 className="modal__title">Удалить проект?</h3>
          <div className="modal__sub">
            Проект «<b style={{ color: "var(--text)" }}>{deleteTarget?.name}</b>» и все его данные
            будут удалены без возможности восстановления.
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <Button
              variant="ghost"
              style={{ flex: 1 }}
              disabled={remove.isPending}
              onClick={() => setDeleteTarget(null)}
            >
              Отмена
            </Button>
            <Button
              variant="danger"
              style={{ flex: 1 }}
              loading={remove.isPending}
              onClick={() => deleteTarget && remove.mutate(deleteTarget.id)}
            >
              Удалить проект
            </Button>
          </div>
        </div>
      </Modal>

      {created && (
        <div className="created-overlay">
          <div className="created-overlay__cube">
            <CubeHero backdrop="transparent" />
          </div>
          <div className="created-overlay__title">«{created.name}» готов</div>
          <div className="created-overlay__sub">
            Модель создана и ждёт в редакторе — введите данные, и через пару минут увидите первые
            расчёты.
          </div>
          <div className="created-overlay__actions">
            <button
              type="button"
              className="created-overlay__cta"
              onClick={() => navigate(`/projects/${created.id}`)}
            >
              Открыть редактор →
            </button>
            <button type="button" className="created-overlay__ghost" onClick={() => setCreated(null)}>
              Остаться в списке
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
