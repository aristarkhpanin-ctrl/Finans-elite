import { useEffect } from "react";
import { currentProduct, PRODUCTS } from "./components/product";

/**
 * Заголовок документа по странице (пакет K, K5): «Результаты — Кофейня — Финанс-Элит».
 *
 * Без него у всех маршрутов был один заголовок «Финансовая модель»: вкладки браузера не
 * различались, а диктор после перехода не мог сказать, где человек оказался, — переход
 * в одностраничном приложении беззвучен (WCAG 2.4.2). Заголовок ставит **каждая страница**
 * — это стережёт перечень-тест по исходникам; объявляет переход `RouteAnnouncer`.
 *
 * Пустые части пропускаются: имя проекта приходит после загрузки, и до неё заголовок —
 * просто «Результаты — Финанс-Элит», а не «Результаты —  — Финанс-Элит».
 */
export function pageTitle(...parts: Array<string | null | undefined | false>): string {
  const product = "Финанс" + PRODUCTS[currentProduct()].brand;
  return [...parts.filter((p): p is string => !!p && !!p.trim()), product].join(" — ");
}

/** Событие «страница поставила заголовок» — по нему `RouteAnnouncer` объявляет переход. */
export const PAGE_TITLE_EVENT = "fe:page-title";

export function usePageTitle(...parts: Array<string | null | undefined | false>): void {
  const title = pageTitle(...parts);
  useEffect(() => {
    document.title = title;
    window.dispatchEvent(new CustomEvent<string>(PAGE_TITLE_EVENT, { detail: title }));
  }, [title]);
}
