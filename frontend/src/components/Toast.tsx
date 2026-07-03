import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Глобальные тосты (Р8, анатомия — «Этап 20»): стек ≤3 в правом верхнем углу,
 * авто-закрытие через 3.2 с, типы success / info / warn / error.
 */
export type ToastKind = "success" | "info" | "warn" | "error";

export interface ToastOptions {
  kind?: ToastKind;
  /** Вторая строка (мелким шрифтом). */
  sub?: string;
}

interface ToastItem {
  id: number;
  kind: ToastKind;
  title: string;
  sub?: string;
}

type ToastFn = (title: string, opts?: ToastOptions) => void;

const ToastContext = createContext<ToastFn | null>(null);

const ICONS: Record<ToastKind, string> = { success: "✓", info: "i", warn: "!", error: "✕" };
const AUTO_DISMISS_MS = 3200;
const MAX_STACK = 3;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback<ToastFn>(
    (title, opts) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev, { id, kind: opts?.kind ?? "info", title, sub: opts?.sub }].slice(-MAX_STACK));
      window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={toast}>
      {children}
      {toasts.length > 0 &&
        createPortal(
          <div className="toast-layer" role="status" aria-live="polite">
            {toasts.map((t) => (
              <div key={t.id} className={`toast toast--${t.kind}`}>
                <span className="toast__ico">{ICONS[t.kind]}</span>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="toast__title">{t.title}</div>
                  {t.sub && <div className="toast__sub">{t.sub}</div>}
                </div>
                <button className="toast__x" onClick={() => dismiss(t.id)} aria-label="Закрыть">
                  ✕
                </button>
              </div>
            ))}
          </div>,
          document.body,
        )}
    </ToastContext.Provider>
  );
}

/** Хук показа тоста: `const toast = useToast(); toast("Сохранено", { kind: "success" })`. */
export function useToast(): ToastFn {
  const fn = useContext(ToastContext);
  const noop = useMemo<ToastFn>(() => () => undefined, []);
  return fn ?? noop;
}
