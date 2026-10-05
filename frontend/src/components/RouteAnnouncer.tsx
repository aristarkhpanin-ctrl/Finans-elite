import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { PAGE_TITLE_EVENT } from "../pageTitle";

/** Пауза после последнего заголовка: имя проекта приходит вслед за самой страницей. */
export const ANNOUNCE_SETTLE_MS = 300;
/** Страница, которая заголовок так и не поставила, всё равно объявляется — тем, что есть. */
export const ANNOUNCE_MAX_WAIT_MS = 3000;

/**
 * Объявление перехода для экранного диктора (пакет K, K5).
 *
 * В одностраничном приложении переход беззвучен: адрес меняется, а фокус остаётся на
 * нажатой ссылке или падает в начало документа, и человек с диктором не знает, что
 * страница сменилась. Здесь живая область говорит заголовок новой страницы.
 *
 * **Объявляется заголовок, который поставила новая страница**, а не тот, что стоит через
 * фиксированную паузу: страница результатов грузится лениво, и через 350 мс заголовок был
 * ещё от редактора — диктор назвал бы не ту страницу (нашёл сквозной тест). Первая
 * загрузка не объявляется — заголовок документа диктор читает сам; уточнение заголовка
 * на той же странице (пришло имя проекта) — тоже: страница уже названа.
 */
export function RouteAnnouncer() {
  const { pathname } = useLocation();
  const current = useRef(pathname);      // путь, на котором приложение сейчас
  const announced = useRef(pathname);    // путь, который уже назван (или первая загрузка)
  const settle = useRef<number | undefined>(undefined);
  const [text, setText] = useState("");

  // Слой раньше эффектов страницы: её заголовок сверяется уже с новым путём.
  useLayoutEffect(() => {
    current.current = pathname;
  }, [pathname]);

  useEffect(() => {
    const say = (title: string) => {
      announced.current = current.current;
      setText(`Открыта страница: ${title}`);
    };
    const onTitle = (e: Event) => {
      if (current.current === announced.current) return;
      const title = (e as CustomEvent<string>).detail;
      window.clearTimeout(settle.current);
      settle.current = window.setTimeout(() => say(title), ANNOUNCE_SETTLE_MS);
    };
    window.addEventListener(PAGE_TITLE_EVENT, onTitle);
    return () => {
      window.removeEventListener(PAGE_TITLE_EVENT, onTitle);
      window.clearTimeout(settle.current);
    };
  }, []);

  useEffect(() => {
    if (pathname === announced.current) return;
    const id = window.setTimeout(() => {
      if (current.current !== announced.current) {
        announced.current = current.current;
        setText(`Открыта страница: ${document.title}`);
      }
    }, ANNOUNCE_MAX_WAIT_MS);
    return () => window.clearTimeout(id);
  }, [pathname]);

  return (
    <div className="sr-only" role="status" aria-live="polite" aria-atomic="true"
         data-testid="route-announcer">
      {text}
    </div>
  );
}
