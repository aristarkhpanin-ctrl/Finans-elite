import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Layout } from "./components/Layout";
import { Splash } from "./components/Splash";
import { RouteAnnouncer } from "./components/RouteAnnouncer";
import { ToastProvider } from "./components/Toast";
import { AuditGroupPage } from "./pages/AuditGroupPage";
import { AuditComparePage } from "./pages/AuditComparePage";
import { AuditHomePage } from "./pages/AuditHomePage";
import { AuditOnboardingPage } from "./pages/AuditOnboardingPage";
import { AuditSubjectPage } from "./pages/AuditSubjectPage";
import { HoldingDetailPage } from "./pages/HoldingDetailPage";
import { HoldingsPage } from "./pages/HoldingsPage";
import { LoginPage } from "./pages/LoginPage";
import { OrganizationPage } from "./pages/OrganizationPage";
import { ProjectEditorPage } from "./pages/ProjectEditorPage";
import { ProjectOnboardingPage } from "./pages/ProjectOnboardingPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ActivatePage } from "./pages/ActivatePage";
import { UnsubscribePage } from "./pages/UnsubscribePage";
import { VerifyEmailPage } from "./pages/VerifyEmailPage";

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
// Служебный раздел платформы (B1) — отдельный чанк: у подавляющего большинства
// пользователей признака сотрудника нет, и грузить им этот код незачем.
const AdminPage = lazy(() => import("./pages/AdminPage").then((m) => ({ default: m.AdminPage })));
// План по ссылке (L4) — тоже отдельный чанк: его открывает посетитель без входа, и
// грузить ему рабочую область незачем.
const SharedPlanPage = lazy(() =>
  import("./pages/SharedPlanPage").then((m) => ({ default: m.SharedPlanPage })),
);

export function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <AppRoutes />
        {/* Один объявитель на всё приложение — и на каркас, и на вход: переход между
            «Вход» и «Регистрация» диктору так же нужен, как между проектами. */}
        <RouteAnnouncer />
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
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      {/* Отписка от обсуждения — тоже до входа: пароль ради «не пишите мне» человек
          искать не станет, он отправит письмо в спам. */}
      <Route path="/comments/unsubscribe" element={<UnsubscribePage />} />
      {/* План по ссылке для инвестора или банка (L4) — без входа: секрет в адресе и есть
          пропуск, а регистрация ради чужого бизнес-плана отпугнула бы того, кому его шлют. */}
      <Route
        path="/s/:token"
        element={
          <Suspense fallback={<Splash />}>
            <SharedPlanPage />
          </Suspense>
        }
      />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/onboarding" element={<ProjectOnboardingPage />} />
        <Route path="/audit" element={<AuditHomePage />} />
        <Route path="/audit/onboarding" element={<AuditOnboardingPage />} />
        <Route path="/audit/group" element={<AuditGroupPage />} />
        <Route path="/audit/compare" element={<AuditComparePage />} />
        <Route path="/audit/:id" element={<AuditSubjectPage />} />
        <Route path="/holdings" element={<HoldingsPage />} />
        <Route path="/holdings/:id" element={<HoldingDetailPage />} />
        <Route path="/organization" element={<OrganizationPage />} />
        {/* Раздел сам отказывает тому, у кого нет признака сотрудника: маршрут не
            прячется, а объясняет отказ — недоступное показывается, а не исчезает. */}
        <Route
          path="/admin"
          element={
            <Suspense fallback={<Splash />}>
              <AdminPage />
            </Suspense>
          }
        />
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
