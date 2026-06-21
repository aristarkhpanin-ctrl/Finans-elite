import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getMe, getMyOrganizations, login as apiLogin, register as apiRegister } from "../api/auth";
import { getOrgId, getToken, setOrgId, setToken } from "../api/client";
import type { LoginPayload, OrganizationMembership, RegisterPayload, User } from "../api/types";

interface AuthState {
  user: User | null;
  organizations: OrganizationMembership[];
  currentOrgId: string | null;
  loading: boolean;
  login: (p: LoginPayload) => Promise<void>;
  register: (p: RegisterPayload) => Promise<void>;
  logout: () => void;
  selectOrg: (orgId: string) => void;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationMembership[]>([]);
  const [currentOrgId, setCurrentOrgId] = useState<string | null>(getOrgId());
  const [loading, setLoading] = useState<boolean>(!!getToken());

  async function loadProfile() {
    const [me, orgs] = await Promise.all([getMe(), getMyOrganizations()]);
    setUser(me);
    setOrganizations(orgs);
    if (orgs.length > 0 && !getOrgId()) {
      setOrgId(orgs[0].id);
      setCurrentOrgId(orgs[0].id);
    }
  }

  useEffect(() => {
    if (!getToken()) return;
    loadProfile().catch(() => logout()).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(p: LoginPayload) {
    const { access_token } = await apiLogin(p);
    setToken(access_token);
    await loadProfile();
  }

  async function register(p: RegisterPayload) {
    const { access_token } = await apiRegister(p);
    setToken(access_token);
    await loadProfile();
  }

  function logout() {
    setToken(null);
    setOrgId(null);
    setUser(null);
    setOrganizations([]);
    setCurrentOrgId(null);
  }

  function selectOrg(orgId: string) {
    setOrgId(orgId);
    setCurrentOrgId(orgId);
  }

  const value = useMemo<AuthState>(
    () => ({ user, organizations, currentOrgId, loading, login, register, logout, selectOrg }),
    [user, organizations, currentOrgId, loading],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth должен использоваться внутри AuthProvider");
  return ctx;
}
