import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { checkout, getPlans, getSubscription, type Plan } from "../../api/org";
import { Button, Card } from "../../components/ui";

function usage(used: number, limit: number | null): string {
  return limit === null ? `${used} / ∞` : `${used} / ${limit}`;
}

export function BillingTab({ orgId }: { orgId: string }) {
  const qc = useQueryClient();
  const [msg, setMsg] = useState("");

  const sub = useQuery({ queryKey: ["subscription", orgId], queryFn: () => getSubscription(orgId) });
  const plans = useQuery({ queryKey: ["plans"], queryFn: getPlans });

  const change = useMutation({
    mutationFn: (code: string) => checkout(orgId, code),
    onSuccess: (res) => {
      if (res.confirmation_url) {
        window.location.assign(res.confirmation_url); // оплата ЮKassa
      } else {
        setMsg("Тариф изменён");
        qc.invalidateQueries({ queryKey: ["subscription", orgId] });
        setTimeout(() => setMsg(""), 2500);
      }
    },
    onError: (e: any) => setMsg(e?.response?.status === 403 ? "Нужны права владельца" : "Не удалось сменить тариф"),
  });

  const planCard = (p: Plan) => {
    const current = sub.data?.plan_code === p.code;
    return (
      <Card key={p.code} style={{ borderColor: current ? "var(--primary)" : undefined }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <strong style={{ fontSize: 16 }}>{p.name}</strong>
          <span className="muted">{p.price_rub.toLocaleString("ru-RU")} ₽/мес</span>
        </div>
        <ul className="muted" style={{ paddingLeft: 18, margin: "10px 0" }}>
          <li>Проектов: {p.max_projects ?? "без лимита"}</li>
          <li>Участников: {p.max_members ?? "без лимита"}</li>
        </ul>
        {current ? (
          <Button variant="ghost" disabled>Текущий тариф</Button>
        ) : (
          <Button onClick={() => change.mutate(p.code)} disabled={change.isPending}>Перейти</Button>
        )}
      </Card>
    );
  };

  return (
    <div>
      {sub.data && (
        <Card style={{ marginBottom: 18 }}>
          <h3 style={{ marginTop: 0 }}>Текущая подписка</h3>
          <div className="form-grid">
            <div><div className="m-label">Тариф</div><div className="m-value" style={{ fontSize: 18 }}>{sub.data.plan_name}</div></div>
            <div><div className="m-label">Статус</div><div style={{ fontWeight: 600 }}>{sub.data.status}</div></div>
            <div><div className="m-label">Проекты</div><div style={{ fontWeight: 600 }}>{usage(sub.data.used_projects, sub.data.max_projects)}</div></div>
            <div><div className="m-label">Участники</div><div style={{ fontWeight: 600 }}>{usage(sub.data.used_members, sub.data.max_members)}</div></div>
          </div>
          {msg && <p style={{ color: "var(--success)" }}>{msg}</p>}
        </Card>
      )}

      <h3>Тарифы</h3>
      {plans.data && (
        <div className="form-grid">{plans.data.map(planCard)}</div>
      )}
    </div>
  );
}
