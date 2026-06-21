import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { getToken } from "../api/client";
import { useAuth } from "./AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { loading } = useAuth();
  if (!getToken()) return <Navigate to="/login" replace />;
  if (loading) return <div className="content muted">Загрузка…</div>;
  return <>{children}</>;
}
