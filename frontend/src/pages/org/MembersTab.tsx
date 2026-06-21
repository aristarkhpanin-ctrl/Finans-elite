import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { addMember, getMembers, roleLabel, ROLES } from "../../api/org";
import { Button, Card } from "../../components/ui";

export function MembersTab({ orgId }: { orgId: string }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("editor");
  const [err, setErr] = useState("");

  const { data, isLoading } = useQuery({ queryKey: ["members", orgId], queryFn: () => getMembers(orgId) });

  const add = useMutation({
    mutationFn: () => addMember(orgId, { email: email.trim(), full_name: fullName.trim(), role }),
    onSuccess: () => {
      setEmail(""); setFullName(""); setErr("");
      qc.invalidateQueries({ queryKey: ["members", orgId] });
    },
    onError: (e: any) => {
      const s = e?.response?.status;
      setErr(s === 403 ? "Недостаточно прав (нужен владелец/администратор)"
        : s === 402 ? "Достигнут лимит участников тарифа" : "Не удалось добавить участника");
    },
  });

  return (
    <div>
      <Card style={{ marginBottom: 18 }}>
        <h3 style={{ marginTop: 0 }}>Добавить участника</h3>
        <div className="form-grid" style={{ alignItems: "end" }}>
          <label className="field"><span>Email</span>
            <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label className="field"><span>Имя</span>
            <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} /></label>
          <label className="field"><span>Роль</span>
            <select className="select" value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select></label>
          <Button onClick={() => add.mutate()} disabled={add.isPending || !email.trim()}>Добавить</Button>
        </div>
        {err && <p className="error">{err}</p>}
      </Card>

      {isLoading && <p className="muted">Загрузка…</p>}
      {data && (
        <div className="list">
          {data.map((m) => (
            <div className="list-item" key={m.user_id}>
              <div>
                <strong>{m.full_name || m.email}</strong>
                <div className="muted">{m.email}</div>
              </div>
              <span className="muted">{roleLabel(m.role)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
