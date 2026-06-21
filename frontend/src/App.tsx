import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { ProjectEditorPage } from "./pages/ProjectEditorPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RegisterPage } from "./pages/RegisterPage";

// Страница результатов тянет recharts — грузим лениво (code-split).
const ProjectResultsPage = lazy(() =>
  import("./pages/ProjectResultsPage").then((m) => ({ default: m.ProjectResultsPage })),
);

export function App() {
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
        <Route path="/projects/:id" element={<ProjectEditorPage />} />
        <Route
          path="/projects/:id/results"
          element={
            <Suspense fallback={<p className="muted">Загрузка…</p>}>
              <ProjectResultsPage />
            </Suspense>
          }
        />
        <Route path="/" element={<Navigate to="/projects" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/projects" replace />} />
    </Routes>
  );
}
