import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { Layout } from "./components/Layout";
import { Splash } from "./components/Splash";
import { ToastProvider } from "./components/Toast";
import { HoldingsPage } from "./pages/HoldingsPage";
import { LoginPage } from "./pages/LoginPage";
import { OrganizationPage } from "./pages/OrganizationPage";
import { ProjectEditorPage } from "./pages/ProjectEditorPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RegisterPage } from "./pages/RegisterPage";

// Страницы с recharts грузим лениво (code-split).
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
    <ToastProvider>
      <AppRoutes />
    </ToastProvider>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/holdings" element={<HoldingsPage />} />
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
