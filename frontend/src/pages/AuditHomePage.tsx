import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  type AuditPeriod,
  type AuditSubjectSummary,
  type ReportingStandard,
  REPORTING_STANDARDS,
  createAuditSubject,
  deleteAuditSubject,
  duplicateAuditSubject,
  emptyAuditModel,
  listAuditSubjects,
} from "../api/audit";
import { IconCopy, IconTrash } from "../components/icons";
import { useToast } from "../components/Toast";
import { Button, Chip, ErrorState, Field, Loading, Modal, SelectField } from "../components/ui";

/**
 * Финанс-Аудит — список дел (макет «Экран 6 — Каркас и список дел»).
 *
 * «Дело» — подпись из макетов; слой хранения остался субъектом анализа
 * (`audit_subjects`, `/api/v1/audit/subjects`), см. docs/FINANS-AUDIT-UI-DECOMPOSITION.md §1.
 *
 * Карточка показывает состояние цели, а не одно имя: светофор диагностики приходит
 * из того же анализа, что и вкладка дела. Скана 24 процедур и вердикта «покупать /
 * торговаться / отказаться» из макета здесь нет — их методики ещё не написаны (фазы
 * 4–5), а рисовать прогресс несуществующей проверки значило бы обещать её наличие.
 */

/** Светофор диагностики → подпись и тон чипа. `null` — отчётности нет. */
const LIGHT: Record<string, { label: string; kind: "active" | "warn" | "problem" }> = {
  ok: { label: "Норма", kind: "active" },
  warning: { label: "Внимание", kind: "warn" },
  risk: { label: "Риск", kind: "problem" },
};

/** Фильтры списка. `null` в `light` — дела без введённой отчётности. */
const FILTERS: [string, string, string | null][] = [
  ["all", "Все", null],
  ["ok", "Норма", "ok"],
  ["warning", "Внимание", "warning"],
  ["risk", "Риск", "risk"],
  ["none", "Без отчётности", null],
];

const PERIOD_KINDS: [string, string][] = [
  ["year", "Год"],
  ["quarter", "Квартал"],
  ["month", "Месяц"],
];

function matches(s: AuditSubjectSummary, key: string): boolean {
  if (key === "all") return true;
  if (key === "none") return s.light === null;
  return s.light === key;
}

/** Дата последней правки коротко: «12 мар 2026». */
function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU",
    { day: "numeric", month: "short", year: "numeric" });
}

export function AuditHomePage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const [filter, setFilter] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [confirm, setConfirm] = useState<AuditSubjectSummary | null>(null);

  // Поля модалки создания. Всё, что здесь спрашивается, действительно есть в модели:
  // выдуманных полей (ИНН, глубина проверки) из макета нет — их некуда сохранить.
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [standard, setStandard] = useState<ReportingStandard>("rsbu");
  const [kind, setKind] = useState<AuditPeriod["kind"]>("year");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["audit-subjects"],
    queryFn: listAuditSubjects,
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["audit-subjects"] });

  const subjects = useMemo(() => data ?? [], [data]);
  const shown = useMemo(() => subjects.filter((s) => matches(s, filter)), [subjects, filter]);
  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const [key] of FILTERS) out[key] = subjects.filter((s) => matches(s, key)).length;
    return out;
  }, [subjects]);

  const create = useMutation({
    mutationFn: () => {
      const model = emptyAuditModel();
      return createAuditSubject(name.trim(), {
        ...model,
        name: name.trim(),
        industry: industry.trim(),
        reporting_standard: standard,
        periods: [{ label: "", kind }],
      });
    },
    onSuccess: (s) => navigate(`/audit/${s.id}`),
    onError: () => toast("Не удалось создать дело", { kind: "error" }),
  });

  const duplicate = useMutation({
    mutationFn: (id: string) => duplicateAuditSubject(id),
    onSuccess: (s) => { invalidate(); toast(`Создана копия: ${s.name}`, { kind: "success" }); },
    onError: () => toast("Не удалось создать копию", { kind: "error" }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteAuditSubject(id),
    onSuccess: () => { invalidate(); setConfirm(null); toast("Дело удалено", { kind: "success" }); },
    onError: () => toast("Не удалось удалить дело", { kind: "error" }),
  });

  function openCreate() {
    setName("");
    setIndustry("");
    setStandard("rsbu");
    setKind("year");
    setCreateOpen(true);
  }

  /** Подзаголовок: сколько дел и сколько из них требуют внимания. */
  const headSub = subjects.length === 0
    ? "Проверка финансового состояния предприятия по фактической отчётности"
    : [`${subjects.length} ${plural(subjects.length, "дело", "дела", "дел")}`,
       counts.risk > 0 ? `${counts.risk} в зоне риска` : null,
       counts.none > 0 ? `${counts.none} без отчётности` : null,
      ].filter(Boolean).join(" · ");

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Дела</h1>
          <div className="page-sub">{headSub}</div>
        </div>
        <Button onClick={openCreate}>＋&nbsp;&nbsp;Новое дело</Button>
      </div>

      {isLoading ? (
        <Loading />
      ) : isError ? (
        <ErrorState text="Не удалось загрузить дела" onRetry={() => refetch()} />
      ) : subjects.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">Ни одного дела</div>
          <div className="tab-empty__sub">
            Заведите дело, введите бухгалтерскую отчётность по периодам — баланс и отчёт
            о финансовых результатах. Дальше появятся аналитическая форма, коэффициенты,
            тренды, диагностика и заключение.
          </div>
          <Button onClick={openCreate}>＋&nbsp;&nbsp;Создать первое дело</Button>
        </div>
      ) : (
        <>
          <div className="case-filters" role="group" aria-label="Фильтр дел">
            {FILTERS.filter(([key]) => key === "all" || counts[key] > 0).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={"case-filter" + (filter === key ? " case-filter--active" : "")}
                aria-pressed={filter === key}
                onClick={() => setFilter(key)}
              >
                {label} · {counts[key]}
              </button>
            ))}
          </div>

          {shown.length === 0 ? (
            <div className="tab-empty">
              <div className="tab-empty__title">В этой группе дел нет</div>
              <div className="tab-empty__sub">Снимите фильтр, чтобы увидеть остальные.</div>
              <Button variant="ghost" onClick={() => setFilter("all")}>Показать все</Button>
            </div>
          ) : (
            <div className="proj-grid">
              {shown.map((s) => (
                <div className="proj-card" key={s.id}>
                  <div>
                    <button type="button" className="proj-card__name"
                            onClick={() => navigate(`/audit/${s.id}`)}>
                      {s.name || "Без названия"}
                    </button>
                    <div className="case-card__meta">
                      {[s.industry || "отрасль не указана",
                        `${s.n_periods} ${plural(s.n_periods, "период", "периода", "периодов")}`,
                       ].join(" · ")}
                    </div>
                  </div>

                  <div className="case-card__chips">
                    {s.light && LIGHT[s.light] ? (
                      <Chip kind={LIGHT[s.light].kind}>{LIGHT[s.light].label}</Chip>
                    ) : (
                      // «Не считалось» — не «в норме»: пустой светофор говорит именно
                      // об отсутствии данных, а не о благополучии.
                      <Chip kind="neutral" dot={false}>Нет отчётности</Chip>
                    )}
                    {!s.balanced && <Chip kind="problem">Баланс не сходится</Chip>}
                  </div>

                  <div className="proj-card__foot">
                    <span className="proj-card__date">{shortDate(s.updated_at)}</span>
                    <div style={{ display: "flex", gap: 6 }}>
                      {/* Подпись называет объект: на экране много одинаковых кнопок,
                          и «Удалить дело» у каждой карточки звучало бы для скринридера
                          неразличимо — а рядом ещё и кнопка подтверждения с тем же
                          именем. Действие должно быть адресным. */}
                      <button type="button" className="icon-action"
                              title={`Дублировать дело «${s.name || "Без названия"}»`}
                              onClick={() => duplicate.mutate(s.id)}>
                        <IconCopy size={15} />
                      </button>
                      <button type="button" className="icon-action icon-action--danger"
                              title={`Удалить дело «${s.name || "Без названия"}»`}
                              onClick={() => setConfirm(s)}>
                        <IconTrash size={15} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Новое дело"
        sub="Реквизиты можно изменить позже на вкладке «Субъект»."
        actions={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)} disabled={create.isPending}>
              Отмена
            </Button>
            <Button onClick={() => create.mutate()} loading={create.isPending}
                    disabled={!name.trim()}>
              Создать
            </Button>
          </>
        }
      >
        <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }}>
          <Field label="Название фирмы-цели" placeholder="ООО «Пример»" value={name}
                 autoFocus disabled={create.isPending}
                 onChange={(e) => setName(e.target.value)} />
          <Field label="Отрасль" placeholder="напр. Перевозки" value={industry}
                 disabled={create.isPending}
                 onChange={(e) => setIndustry(e.target.value)} />
          <SelectField
            label="Основа отчётности" value={standard} disabled={create.isPending}
            options={REPORTING_STANDARDS}
            hint="Признак, а не пересчёт: платформа фиксирует основу, но не трансформирует одну в другую. Свод группы не смешивает участников с разными основами."
            onChange={(v) => setStandard(v as ReportingStandard)}
          />
          <SelectField
            label="Периодичность отчётности" value={kind} disabled={create.isPending}
            options={PERIOD_KINDS}
            hint="Задаёт длину периода: показатели «в днях» считаются по ней, а потоковые приводятся к году."
            onChange={(v) => setKind(v as AuditPeriod["kind"])}
          />
        </form>
      </Modal>

      <Modal
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        title="Удалить дело?"
        actions={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)} disabled={remove.isPending}>
              Отмена
            </Button>
            <Button variant="danger" loading={remove.isPending}
                    onClick={() => confirm && remove.mutate(confirm.id)}>
              Удалить дело
            </Button>
          </>
        }
      >
        {/* Подтверждение называет последствие и объект, а не спрашивает «вы уверены?». */}
        <div className="page-sub">
          Дело «{confirm?.name || "Без названия"}» будет удалено вместе с введённой
          отчётностью за {confirm?.n_periods ?? 0}&nbsp;
          {plural(confirm?.n_periods ?? 0, "период", "периода", "периодов")}. Отменить
          удаление нельзя.
        </div>
      </Modal>
    </div>
  );
}

/** Русское склонение по числу: 1 дело, 2 дела, 5 дел. */
function plural(n: number, one: string, few: string, many: string): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return many;
  const mod10 = n % 10;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}
