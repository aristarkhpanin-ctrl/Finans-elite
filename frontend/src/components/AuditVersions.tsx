import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { httpDetail } from "../api/client";
import {
  createAuditVersion,
  deleteAuditVersion,
  diffAuditVersion,
  listAuditVersions,
  restoreAuditVersion,
  type AuditVersionDiff,
} from "../api/audit";
import { useToast } from "./Toast";
import { Button } from "./ui";
import { fmtMillions, percent } from "../format";

/**
 * Версии дела: снимки модели проверки, диф и восстановление.
 *
 * Проверка идёт итерациями — пришли выписки, реестр обязательств поменялся, вердикт
 * уехал. Комитет спрашивает «что изменилось с прошлой недели» и «какая версия
 * подписана», и по одной рабочей модели ответить нечем.
 *
 * Сводка в списке — **та, что была на момент снимка**: версия описывает прошлое, и
 * пересчитывать её по сегодняшней отчётности значило бы стереть то, ради чего снимок
 * и делали. Пустое дело вердикта не имеет вовсе — прочерк, а не «в норме».
 */

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", year: "numeric",
                                          hour: "2-digit", minute: "2-digit" });

const KIND_META: Record<string, { label: string; cls: string }> = {
  added: { label: "добавлено", cls: "vch--add" },
  removed: { label: "удалено", cls: "vch--rem" },
  changed: { label: "изменено", cls: "vch--chg" },
};

/** Подписи вердикта — те же слова, что в шапке дела. */
const VERDICT: Record<string, string> = {
  ok: "В норме",
  warning: "Требует внимания",
  risk: "Высокий риск",
  unreliable: "Данные ненадёжны",
};

const fmtVal = (v: unknown): string =>
  v === null || v === undefined ? "∅" : Array.isArray(v) ? `[${v.length}]` : String(v);

/**
 * Величина дела в человеческом виде. Вердикт — слово, охват — процент, деньги — суммой;
 * `null` печатается прочерком: «не считалось» и «ноль» — разные вещи.
 */
function fmtMetric(key: string, value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (key === "verdict") return VERDICT[value] ?? value;
  if (key === "coverage") return percent(value, 0);
  if (key === "risk_flags" || key === "warning_flags") return value;
  return fmtMillions(value, { digits: 2 });
}

function DiffView({ diff }: { diff: AuditVersionDiff }) {
  const changed = diff.metric_changes.filter((m) => (m.old ?? null) !== (m.new ?? null));
  return (
    <div className="vdiff">
      <div className="rsection-label">Что изменилось в деле</div>
      {changed.length === 0 ? (
        <div className="field-note">Вердикт, находки, охват и оценка не изменились.</div>
      ) : (
        <div className="contrib-wrap">
          <div className="contrib-row contrib-row--head">
            <div className="contrib-label">Величина</div>
            <div className="contrib-cell">Было</div>
            <div className="contrib-cell">Стало</div>
          </div>
          {changed.map((m) => (
            <div className="contrib-row" key={m.key}>
              <div className="contrib-label">{m.label}</div>
              <div className="contrib-cell">{fmtMetric(m.key, m.old)}</div>
              <div className="contrib-cell">{fmtMetric(m.key, m.new)}</div>
            </div>
          ))}
        </div>
      )}

      <div className="rsection-label" style={{ marginTop: 16 }}>
        Изменения отчётности и допущений ({diff.model_changes.length}
        {diff.model_changes_truncated ? "+" : ""})
      </div>
      {diff.model_changes.length === 0 ? (
        <div className="field-note">Данные дела совпадают.</div>
      ) : (
        <div className="vch-list">
          {diff.model_changes.map((c, i) => {
            const meta = KIND_META[c.kind] ?? KIND_META.changed;
            return (
              <div className="vch-row" key={`${c.path}:${i}`}>
                <span className={"vch-badge " + meta.cls}>{meta.label}</span>
                <code className="vch-path">{c.path}</code>
                <span className="vch-vals">
                  {c.kind !== "added" && <span className="vch-old">{fmtVal(c.old)}</span>}
                  {c.kind === "changed" && <span className="vch-arrow">→</span>}
                  {c.kind !== "removed" && <span className="vch-new">{fmtVal(c.new)}</span>}
                </span>
              </div>
            );
          })}
          {diff.model_changes_truncated && (
            <div className="field-note">
              Показаны первые {diff.model_changes.length} изменений (список усечён).
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AuditVersions({ subjectId }: { subjectId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [label, setLabel] = useState("");
  const [openDiff, setOpenDiff] = useState<string | null>(null);

  const versions = useQuery({
    queryKey: ["audit-versions", subjectId],
    queryFn: () => listAuditVersions(subjectId),
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["audit-versions", subjectId] });

  const save = useMutation({
    mutationFn: () => createAuditVersion(subjectId, label.trim()),
    onSuccess: () => { setLabel(""); invalidate(); toast("Версия сохранена", { kind: "success" }); },
    onError: (e) => toast(httpDetail(e) ?? "Не удалось сохранить версию", { kind: "error" }),
  });

  const remove = useMutation({
    mutationFn: (vid: string) => deleteAuditVersion(subjectId, vid),
    onSuccess: () => { setOpenDiff(null); invalidate(); },
  });

  const restore = useMutation({
    mutationFn: (vid: string) => restoreAuditVersion(subjectId, vid),
    onSuccess: () => {
      // Восстановление меняет модель дела: и карточка, и анализ, и риски устарели.
      qc.invalidateQueries({ queryKey: ["audit-subject", subjectId] });
      qc.invalidateQueries({ queryKey: ["audit-analysis", subjectId] });
      qc.invalidateQueries({ queryKey: ["audit-risk", subjectId] });
      toast("Модель версии восстановлена в деле", { kind: "success" });
    },
    onError: (e) => toast(httpDetail(e) ?? "Не удалось восстановить", { kind: "error" }),
  });

  const diff = useQuery({
    queryKey: ["audit-version-diff", subjectId, openDiff],
    queryFn: () => diffAuditVersion(subjectId, openDiff!, "current"),
    enabled: openDiff !== null,
  });

  return (
    <div>
      <div className="tab-head" style={{ marginBottom: 12 }}>
        <div style={{ minWidth: 0 }}>
          <div className="audit-block__title" style={{ marginBottom: 2 }}>Версии дела</div>
          <div className="page-sub">
            Снимок модели проверки на дату: что было в деле, когда заключение уходило в
            комитет, и что изменилось с тех пор.
          </div>
        </div>
      </div>

      <div className="vsave">
        <input
          className="vsave__input"
          placeholder="Название версии, напр. «Перед инвесткомитетом 12.09»"
          aria-label="Название версии"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <Button loading={save.isPending} onClick={() => save.mutate()}>
          Сохранить версию
        </Button>
      </div>

      {versions.isPending && <div className="field-note">Загрузка версий…</div>}
      {versions.data && versions.data.length === 0 && (
        <div className="tab-empty">
          <div className="tab-empty__title">Версий пока нет</div>
          <div className="tab-empty__sub">
            Сохраните дело версией перед тем, как отдавать заключение: потом будет видно,
            что изменилось, и можно будет вернуться к подписанному состоянию.
          </div>
        </div>
      )}

      {versions.data && versions.data.length > 0 && (
        <div className="vlist">
          {versions.data.map((v) => (
            <div className="line-card" key={v.id}>
              <div className="vrow">
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="vrow__label">{v.label}</div>
                  <div className="vrow__meta">
                    {fmtDate(v.created_at)}
                    {/* Сводка снимка: вердикт на тот момент, а не сегодняшний. */}
                    {v.verdict != null
                      ? <> · {VERDICT[v.verdict] ?? v.verdict}</>
                      : <> · отчётности тогда не было</>}
                    {v.risk_flags != null && v.risk_flags > 0 && (
                      <> · флагов риска {v.risk_flags}</>
                    )}
                    {v.equity_value != null && (
                      <> · доля {fmtMillions(v.equity_value, { digits: 1 })}</>
                    )}
                  </div>
                </div>
                <div className="vrow__actions">
                  <Button variant="ghost"
                          onClick={() => setOpenDiff(openDiff === v.id ? null : v.id)}>
                    {openDiff === v.id ? "Скрыть" : "Сравнить с текущим"}
                  </Button>
                  <Button variant="ghost"
                          loading={restore.isPending && restore.variables === v.id}
                          onClick={() => restore.mutate(v.id)}>
                    Восстановить
                  </Button>
                  <Button variant="ghost"
                          loading={remove.isPending && remove.variables === v.id}
                          onClick={() => remove.mutate(v.id)}>
                    Удалить
                  </Button>
                </div>
              </div>
              {openDiff === v.id && (
                <div style={{ marginTop: 14 }}>
                  {diff.isPending && <div className="field-note">Считаем изменения…</div>}
                  {diff.isError && (
                    <div className="field-note">
                      {httpDetail(diff.error) ?? "Не удалось построить диф."}
                    </div>
                  )}
                  {diff.data && <DiffView diff={diff.data} />}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
