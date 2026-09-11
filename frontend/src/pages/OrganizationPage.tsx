import { useState } from "react";
import { roleLabel } from "../api/org";
import { useAuth } from "../auth/AuthContext";
import { BillingTab } from "./org/BillingTab";
import { AuditLogTab } from "./org/AuditLogTab";
import { ProfileTab } from "./org/ProfileTab";
import { MembersTab } from "./org/MembersTab";
import { ActivityTab } from "./org/ActivityTab";
import { BenchmarksTab } from "./org/BenchmarksTab";
import { ChecklistsTab } from "./org/ChecklistsTab";
import { ApiKeysTab } from "./org/ApiKeysTab";

const TABS = [
  ["members", "Участники"],
  ["activity", "Активность"],
  ["profile", "Профиль"],
  ["benchmarks", "Ориентиры"],
  ["checklists", "Чек-листы"],
  ["apikeys", "Ключи API"],
  ["log", "Журнал доступа"],
  ["billing", "Тариф и оплата"],
] as const;

export function OrganizationPage() {
  const { currentOrgId, organizations, user } = useAuth();
  const [tab, setTab] = useState<string>("members");
  /**
   * Отбор, с которым открыть журнал. Заполняется с экрана участников («действия
   * участника») — так «кто что делал» отвечает **журнал**, а не второй список рядом,
   * который со временем разошёлся бы с ним.
   */
  const [logActor, setLogActor] = useState("");
  const org = organizations.find((o) => o.id === currentOrgId);

  if (!currentOrgId) return <p className="muted">Организация не выбрана</p>;

  const myRole = org?.role ?? "viewer";
  const canManageOrg = myRole === "owner" || myRole === "admin";

  return (
    <div>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title">{org?.name ?? "Организация"}</h1>
          <div className="page-sub">Участники, роли, отраслевые ориентиры, тариф и оплата.</div>
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

      {tab === "members" && (
        <MembersTab orgId={currentOrgId} myRole={myRole} myUserId={user?.id ?? ""}
                    onShowActions={canManageOrg
                      ? (email) => { setLogActor(email); setTab("log"); }
                      : undefined} />
      )}
      {/* Журнал видит только тот, кто управляет организацией: право org.manage.
          Аналитик работает с делами — следы чужой работы не его дело. Вкладка не
          прячется, а объясняет отказ: недоступное показывается, а не исчезает. */}
      {/* Сводка активности видна тем, кто отвечает за организацию, — тот же довод,
          что у журнала: она отвечает на вопрос об **остальных** участниках. */}
      {tab === "activity" && (canManageOrg
        ? <ActivityTab orgId={currentOrgId} />
        : <div className="tab-empty">
            <div className="tab-empty__title">Сводка доступна администраторам</div>
            <div className="tab-empty__sub">
              Активность показывает, кто из участников работает и над чем, поэтому её
              видят владелец и администратор. Ваша роль — {roleLabel(myRole)}.
            </div>
          </div>)}
      {tab === "profile" && <ProfileTab />}
      {/* Ориентиры принадлежат организации, а не делу: одна и та же медиана фонда
          читается во всех делах, и вести её в каждом значило бы её размножить. */}
      {tab === "benchmarks" && <BenchmarksTab orgId={currentOrgId} canManage={canManageOrg} />}
      {/* Чек-листы принадлежат организации, а не делу: один и тот же набор процедур
          применяют ко всем делам, и вести его в каждом значило бы его размножить. */}
      {tab === "checklists" && <ChecklistsTab orgId={currentOrgId} canManage={canManageOrg} />}
      {/* Ключ — дверь в данные организации, поэтому заводит его тот же, кто заводит
          участников. Видеть список может каждый участник: «кто ходит в наши данные» —
          не секрет от тех, чьи это данные. */}
      {tab === "apikeys" && <ApiKeysTab orgId={currentOrgId} canManage={canManageOrg} />}
      {tab === "log" && (canManageOrg
        ? <AuditLogTab orgId={currentOrgId} initialActor={logActor} />
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
