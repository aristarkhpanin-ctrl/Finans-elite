import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

/** Пауза перед объявлением: страница успевает поставить свой заголовок (`usePageTitle`). */
export const ANNOUNCE_DELAY_MS = 350;

/**
 * Объявление перехода для экранного диктора (пакет K, K5).
 *
 * В одностраничном приложении переход беззвучен: адрес меняется, а фокус остаётся на
 * нажатой ссылке или падает в начало документа, и человек с диктором не знает, что
 * страница сменилась. Здесь живая область говорит заголовок новой страницы. Первая
 * загрузка не объявляется — заголовок документа диктор читает сам. Переход внутри той же
 * страницы (смена `?tab=`) — тоже: он объявляет себя вкладками.
 */
export function RouteAnnouncer() {
  const { pathname } = useLocation();
  const last = useRef(pathname);
  const [text, setText] = useState("");

  useEffect(() => {
    if (pathname === last.current) return;
    last.current = pathname;
    const id = window.setTimeout(() => setText(`Открыта страница: ${document.title}`),
                                 ANNOUNCE_DELAY_MS);
    return () => window.clearTimeout(id);
  }, [pathname]);

  return (
    <div className="sr-only" role="status" aria-live="polite" aria-atomic="true"
         data-testid="route-announcer">
      {text}
    </div>
  );
}
