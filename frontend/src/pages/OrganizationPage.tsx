import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { BillingTab } from "./org/BillingTab";
import { MembersTab } from "./org/MembersTab";

const TABS = [
  ["members", "Участники"],
  ["billing", "Тариф и оплата"],
] as const;

export function OrganizationPage() {
  const { currentOrgId, organizations, user } = useAuth();
  const [tab, setTab] = useState<string>("members");
  const org = organizations.find((o) => o.id === currentOrgId);

  if (!currentOrgId) return <p className="muted">Организация не выбрана</p>;

  const myRole = org?.role ?? "viewer";

  return (
    <div>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title">{org?.name ?? "Организация"}</h1>
          <div className="page-sub">Участники, роли, тариф и оплата.</div>
        </div>
      </div>

      <div className="etabs-wrap" style={{ margin: "0 0 20px", borderTop: "none", padding: 0 }}>
        <div className="etabs">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={"etab" + (tab === key ? " etab--active" : "")}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === "members" && <MembersTab orgId={currentOrgId} myRole={myRole} myUserId={user?.id ?? ""} />}
      {tab === "billing" && <BillingTab orgId={currentOrgId} canManage={myRole === "owner" || myRole === "admin"} />}
    </div>
  );
}
