import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { BillingTab } from "./org/BillingTab";
import { MembersTab } from "./org/MembersTab";

const TABS = [
  ["members", "Участники"],
  ["billing", "Тариф и оплата"],
] as const;

export function OrganizationPage() {
  const { currentOrgId, organizations } = useAuth();
  const [tab, setTab] = useState<string>("members");
  const org = organizations.find((o) => o.id === currentOrgId);

  if (!currentOrgId) return <p className="muted">Организация не выбрана</p>;

  return (
    <div>
      <h1>{org?.name ?? "Организация"}</h1>
      <div className="tabs">
        {TABS.map(([key, label]) => (
          <button key={key} className={`tab ${tab === key ? "tab--active" : ""}`} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "members" && <MembersTab orgId={currentOrgId} />}
      {tab === "billing" && <BillingTab orgId={currentOrgId} />}
    </div>
  );
}
