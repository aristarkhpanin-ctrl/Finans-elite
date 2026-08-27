import { useState } from "react";
import { roleLabel } from "../api/org";
import { useAuth } from "../auth/AuthContext";
import { BillingTab } from "./org/BillingTab";
import { AuditLogTab } from "./org/AuditLogTab";
import { MembersTab } from "./org/MembersTab";

const TABS = [
  ["members", "Участники"],
  ["log", "Журнал доступа"],
  ["billing", "Тариф и оплата"],
] as const;

export function OrganizationPage() {
  const { currentOrgId, organizations, user } = useAuth();
  const [tab, setTab] = useState<string>("members");
  const org = organizations.find((o) => o.id === currentOrgId);

  if (!currentOrgId) return <p className="muted">Организация не выбрана</p>;

  const myRole = org?.role ?? "viewer";
  const canManageOrg = myRole === "owner" || myRole === "admin";

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
      {/* Журнал видит только тот, кто управляет организацией: право org.manage.
          Аналитик работает с делами — следы чужой работы не его дело. Вкладка не
          прячется, а объясняет отказ: недоступное показывается, а не исчезает. */}
      {tab === "log" && (canManageOrg
        ? <AuditLogTab orgId={currentOrgId} />
        : <div className="tab-empty">
            <div className="tab-empty__title">Журнал доступен администраторам</div>
            <div className="tab-empty__sub">
              Записи журнала показывают действия всех участников организации, поэтому
              их видят владелец и администратор. Ваша роль — {roleLabel(myRole)}.
            </div>
          </div>)}
      {tab === "billing" && <BillingTab orgId={currentOrgId} canManage={canManageOrg} />}
    </div>
  );
}
