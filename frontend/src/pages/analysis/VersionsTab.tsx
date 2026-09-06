import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { httpDetail } from "../../api/client";
import {
  createVersion,
  deleteVersion,
  diffVersion,
  listVersions,
  restoreVersion,
  type VersionDiff,
} from "../../api/versions";
import { useToast } from "../../components/Toast";
import { Button } from "../../components/ui";
import { fmtMillions, percent } from "../../format";

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", year: "numeric",
                                          hour: "2-digit", minute: "2-digit" });

const KIND_META: Record<string, { label: string; cls: string }> = {
  added: { label: "добавлено", cls: "vch--add" },
  removed: { label: "удалено", cls: "vch--rem" },
  changed: { label: "изменено", cls: "vch--chg" },
};

const fmtVal = (v: unknown): string =>
  v === null || v === undefined ? "∅" : Array.isArray(v) ? `[${v.length}]` : String(v);

function DiffView({ diff }: { diff: VersionDiff }) {
  const metricChanged = diff.metric_changes.filter((m) => (m.old ?? null) !== (m.new ?? null));
  return (
    <div className="vdiff">
      <div className="rsection-label">Показатели эффективности</div>
      {metricChanged.length === 0 ? (
        <div className="field-note">Показатели не изменились.</div>
      ) : (
        <div className="contrib-wrap">
          <div className="contrib-row contrib-row--head">
            <div className="contrib-label">Показатель</div>
            <div className="contrib-cell">Было</div>
            <div className="contrib-cell">Стало</div>
          </div>
          {metricChanged.map((m) => (
            <div className="contrib-row" key={m.key}>
              <div className="contrib-label">{m.label}</div>
              <div className="contrib-cell">{m.key.includes("irr") ? percent(m.old, 1) : fmtMillions(m.old, { digits: 2 })}</div>
              <div className="contrib-cell">{m.key.includes("irr") ? percent(m.new, 1) : fmtMillions(m.new, { digits: 2 })}</div>
            </div>
          ))}
        </div>
      )}

      <div className="rsection-label" style={{ marginTop: 16 }}>
        Изменения модели ({diff.model_changes.length}{diff.model_changes_truncated ? "+" : ""})
      </div>
      {diff.model_changes.length === 0 ? (
        <div className="field-note">Данные модели совпадают.</div>
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
            <div className="field-note">Показаны первые {diff.model_changes.length} изменений (список усечён).</div>
          )}
        </div>
      )}
    </div>
  );
}

/** Вкладка «Версии»: снимки модели, диф с текущей рабочей моделью, восстановление. */
export function VersionsTab({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [label, setLabel] = useState("");
  const [openDiff, setOpenDiff] = useState<string | null>(null);

  const versions = useQuery({
    queryKey: ["versions", projectId],
    queryFn: () => listVersions(projectId),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["versions", projectId] });

  const save = useMutation({
    mutationFn: () => createVersion(projectId, label.trim()),
    onSuccess: () => { setLabel(""); invalidate(); toast("Версия сохранена", { kind: "success" }); },
    onError: (e) => toast(httpDetail(e) ?? "Не удалось сохранить версию", { kind: "error" }),
  });

  const remove = useMutation({
    mutationFn: (vid: string) => deleteVersion(projectId, vid),
    onSuccess: () => { setOpenDiff(null); invalidate(); },
  });

  const restore = useMutation({
    mutationFn: (vid: string) => restoreVersion(projectId, vid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      qc.invalidateQueries({ queryKey: ["calc", projectId] });
      toast("Модель версии восстановлена в редакторе", { kind: "success" });
    },
    onError: (e) => toast(httpDetail(e) ?? "Не удалось восстановить", { kind: "error" }),
  });

  const diff = useQuery({
    queryKey: ["version-diff", projectId, openDiff],
    queryFn: () => diffVersion(projectId, openDiff!, "current"),
    enabled: openDiff !== null,
  });

  return (
    <div>
      <div className="an-head">
        <div style={{ minWidth: 0 }}>
          <div className="an-head__title">Версии проекта</div>
          <div className="an-head__sub">
            Снимки модели и анализ изменений: сравнение сохранённой версии с текущей рабочей моделью.
          </div>
        </div>
      </div>

      <div className="vsave">
        <input
          className="vsave__input"
          placeholder="Название версии (необязательно), напр. «Базовый сценарий»"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <Button loading={save.isPending} onClick={() => save.mutate()}>
          Сохранить текущую версию
        </Button>
      </div>

      {versions.isPending && <div className="field-note">Загрузка версий…</div>}
      {versions.data && versions.data.length === 0 && (
        <div className="setup-ph">
          <div className="setup-ph__title">Версий пока нет</div>
          <div className="setup-ph__sub">
            Сохраните текущую модель как версию — потом сможете сравнить изменения и вернуться к ней.
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
                    {v.npv != null && <> · NPV {fmtMillions(v.npv, { digits: 1 })}</>}
                    {v.irr_annual != null && <> · IRR {percent(v.irr_annual, 1)}</>}
                  </div>
                </div>
                <div className="vrow__actions">
                  <Button variant="ghost"
                          onClick={() => setOpenDiff(openDiff === v.id ? null : v.id)}>
                    {openDiff === v.id ? "Скрыть" : "Сравнить с текущей"}
                  </Button>
                  <Button variant="ghost" loading={restore.isPending && restore.variables === v.id}
                          onClick={() => restore.mutate(v.id)}>
                    Восстановить
                  </Button>
                  <Button variant="ghost" loading={remove.isPending && remove.variables === v.id}
                          onClick={() => remove.mutate(v.id)}>
                    Удалить
                  </Button>
                </div>
              </div>
              {openDiff === v.id && (
                <div style={{ marginTop: 14 }}>
                  {diff.isPending && <div className="field-note">Считаем изменения…</div>}
                  {diff.isError && (
                    <div className="field-note">{httpDetail(diff.error) ?? "Не удалось построить диф."}</div>
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
