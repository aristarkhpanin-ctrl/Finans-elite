import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getChecklists, putChecklists, type ChecklistIn } from "../../api/org";
import { httpFieldError } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, Field, Loading } from "../../components/ui";

/**
 * Свои чек-листы организации (D4) — для дел «Финанс-Аудита».
 *
 * **Отраслевого каталога у платформы нет и не будет**: он утверждал бы, что именно
 * проверяют в конкретной отрасли, а такой методики у платформы нет. Здесь другое —
 * чек-лист пишут аналитики самой организации, и он принадлежит ей. Тот же приём, что с
 * отраслевыми ориентирами, где отказ от рыночных медиан стал функцией «ваш ориентир, а
 * не рынок».
 *
 * Правится как таблица — сохраняется целиком: что на экране, то и в хранилище.
 */
export function ChecklistsTab({ orgId, canManage }: { orgId: string; canManage: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [rows, setRows] = useState<ChecklistIn[]>([]);
  const [dirty, setDirty] = useState(false);

  const { data, isLoading } = useQuery({ queryKey: ["checklists", orgId],
                                         queryFn: () => getChecklists(orgId) });
  useEffect(() => {
    if (data) setRows(data.map((c) => ({ name: c.name, scope: c.scope, items: c.items })));
  }, [data]);

  const save = useMutation({
    mutationFn: () => putChecklists(orgId, rows),
    onSuccess: () => {
      setDirty(false);
      qc.invalidateQueries({ queryKey: ["checklists", orgId] });
      toast("Чек-листы сохранены", { kind: "success" });
    },
    // Отказ называет поле: правка уходит целиком, и одна непонятая строка иначе
    // отклоняла бы всё под общим «не удалось сохранить».
    onError: (e: unknown) => toast(httpFieldError(e) ?? "Не удалось сохранить",
                                   { kind: "error" }),
  });

  const patch = (i: number, over: Partial<ChecklistIn>) => {
    setRows(rows.map((r, j) => (j === i ? { ...r, ...over } : r)));
    setDirty(true);
  };

  if (isLoading) return <Loading />;

  return (
    <div style={{ display: "grid", gap: 18, maxWidth: 760 }}>
      <div className="audit-block">
        <div className="audit-block__title">Свои чек-листы проверки</div>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Наборы процедур, которые ваша организация применяет к делам. Отраслевого
          каталога у платформы <b>нет</b>: он утверждал бы, что именно проверяют в
          конкретной отрасли, а такой методики у неё нет. Эти чек-листы пишете вы —
          применённые к делу, они становятся процедурами аналитика, и{" "}
          <b>платформа их не выполняет</b>.
        </p>

        {rows.length === 0 && (
          <div className="mnote">Чек-листов пока нет. Заведите первый — и перестанете
            перепечатывать одни и те же процедуры в каждое новое дело.</div>
        )}

        {rows.map((row, i) => (
          <div className="audit-block" key={i} style={{ marginTop: 12 }}>
            <Field label="Название" value={row.name} disabled={!canManage}
                   placeholder="Проверка производственной компании"
                   onChange={(e) => patch(i, { name: e.target.value })} />
            <Field label="Когда применяем" value={row.scope ?? ""} disabled={!canManage}
                   placeholder="Производство, выручка от 500 млн"
                   note="Свободная подпись автора, а не классификатор: платформа по ней ничего не выбирает."
                   onChange={(e) => patch(i, { scope: e.target.value })} />
            <label className="auth-label" style={{ display: "block", marginBottom: 6 }}>
              Процедуры — по одной в строке
            </label>
            <textarea
              className="input"
              rows={Math.max(3, (row.items ?? []).length + 1)}
              aria-label={`Процедуры чек-листа ${i + 1}`}
              disabled={!canManage}
              style={{ width: "100%", height: "auto", padding: 10, fontSize: 12.5 }}
              value={(row.items ?? []).join("\n")}
              onChange={(e) => patch(i, { items: e.target.value.split("\n") })}
            />
            {canManage && (
              <Button variant="ghost" onClick={() => {
                setRows(rows.filter((_, j) => j !== i));
                setDirty(true);
              }}>Удалить чек-лист</Button>
            )}
          </div>
        ))}

        {canManage ? (
          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <Button variant="ghost" onClick={() => {
              setRows([...rows, { name: "", scope: "", items: [] }]);
              setDirty(true);
            }}>＋&nbsp;&nbsp;Чек-лист</Button>
            <Button onClick={() => save.mutate()} loading={save.isPending}
                    disabled={!dirty}>Сохранить</Button>
          </div>
        ) : (
          <p className="muted" style={{ marginTop: 12 }}>
            🔒 Править чек-листы может владелец организации. Применять их к делам может
            каждый, кто с делами работает.
          </p>
        )}
      </div>
    </div>
  );
}
