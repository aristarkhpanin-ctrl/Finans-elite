import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

/**
 * Граница ошибок: ловит исключения рендера в дереве ниже и показывает понятный экран
 * вместо «белого экрана смерти». Намеренно использует только базовые элементы — чтобы
 * фолбэк работал, даже если сломан один из UI-компонентов.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Точка для отправки в сервис ошибок в проде (Sentry и т.п.).
    console.error("Ошибка рендера интерфейса:", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="error-state" role="alert" style={{ maxWidth: 460, margin: "18vh auto" }}>
          <div className="error-state__ico">!</div>
          <div className="error-state__title">Что-то пошло не так</div>
          <p className="muted" style={{ margin: "6px 0 16px" }}>
            Непредвиденная ошибка в интерфейсе. Перезагрузите страницу — данные проекта
            сохранены на сервере.
          </p>
          <button type="button" className="btn" onClick={() => window.location.reload()}>
            Перезагрузить
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
