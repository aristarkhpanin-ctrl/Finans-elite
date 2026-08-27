import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Layout } from "./components/Layout";
import { Splash } from "./components/Splash";
import { ToastProvider } from "./components/Toast";
import { AuditGroupPage } from "./pages/AuditGroupPage";
import { AuditHomePage } from "./pages/AuditHomePage";
import { AuditSubjectPage } from "./pages/AuditSubjectPage";
import { HoldingDetailPage } from "./pages/HoldingDetailPage";
import { HoldingsPage } from "./pages/HoldingsPage";
import { LoginPage } from "./pages/LoginPage";
import { OrganizationPage } from "./pages/OrganizationPage";
import { ProjectEditorPage } from "./pages/ProjectEditorPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ActivatePage } from "./pages/ActivatePage";

// Тяжёлые страницы результатов/анализа грузим лениво (code-split).
const ProjectResultsPage = lazy(() =>
  import("./pages/ProjectResultsPage").then((m) => ({ default: m.ProjectResultsPage })),
);
// Dev-песочница UI-кита: только в DEV-сборке (в прод-бандл не попадает).
const DevUiPage = import.meta.env.DEV
  ? lazy(() => import("./pages/DevUiPage").then((m) => ({ default: m.DevUiPage })))
  : null;
const ProjectAnalysisPage = lazy(() =>
  import("./pages/ProjectAnalysisPage").then((m) => ({ default: m.ProjectAnalysisPage })),
);

export function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <AppRoutes />
      </ToastProvider>
    </ErrorBoundary>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      {/* Активация приглашения — до входа: пароля у приглашённого ещё нет. */}
      <Route path="/activate" element={<ActivatePage />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/audit" element={<AuditHomePage />} />
        <Route path="/audit/group" element={<AuditGroupPage />} />
        <Route path="/audit/:id" element={<AuditSubjectPage />} />
        <Route path="/holdings" element={<HoldingsPage />} />
        <Route path="/holdings/:id" element={<HoldingDetailPage />} />
        <Route path="/organization" element={<OrganizationPage />} />
        <Route path="/projects/:id" element={<ProjectEditorPage />} />
        <Route
          path="/projects/:id/results"
          element={
            <Suspense fallback={<Splash />}>
              <ProjectResultsPage />
            </Suspense>
          }
        />
        <Route
          path="/projects/:id/analysis"
          element={
            <Suspense fallback={<Splash />}>
              <ProjectAnalysisPage />
            </Suspense>
          }
        />
        <Route path="/" element={<Navigate to="/projects" replace />} />
      </Route>
      {DevUiPage && (
        <Route
          path="/dev/ui"
          element={
            <Suspense fallback={<Splash />}>
              <DevUiPage />
            </Suspense>
          }
        />
      )}
      <Route path="*" element={<Navigate to="/projects" replace />} />
    </Routes>
  );
}
