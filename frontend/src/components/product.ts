// Продукт платформы: «Финанс-Элит» (бизнес-план) и «Финанс-Аудит» (анализ факта).
// Активный продукт задаёт тему через атрибут data-product на <html> (см. styles.css:
// набор фиолетовых токенов для data-product="audit"). Определяется по маршруту.

export type Product = "business" | "audit";

/** Раздел боковой навигации: заголовок и пункты `[маршрут, подпись]`. */
export interface RailSection {
  title: string;
  items: readonly (readonly [string, string])[];
}

export interface ProductMeta {
  id: Product;
  brand: string;        // слово в шапке после «Финанс»
  home: string;         // корневой маршрут продукта
  nav: readonly (readonly [string, string])[];
  cubeAccent: [string, string];   // акценты куб-марки [яркий, глубокий] под тему продукта
  /**
   * Боковая навигация (макет «Финанс Аудит», Экран 6). Есть только у продуктов, чей
   * каркас её предусматривает: «Элит» остаётся на горизонтальной навигации в шапке —
   * он уже соответствует своим макетам (modal-redesign, Этап 3), и менять его каркас
   * ради второго продукта незачем. Задан rail → навигация уезжает из шапки в него.
   */
  rail?: readonly RailSection[];
}

export const PRODUCTS: Record<Product, ProductMeta> = {
  business: {
    id: "business",
    brand: "-Элит",
    home: "/projects",
    nav: [
      ["/projects", "Проекты"],
      ["/holdings", "Холдинги"],
      ["/organization", "Организация"],
    ],
    cubeAccent: ["#7FEE64", "#1FAE68"],   // зелёный
  },
  audit: {
    id: "audit",
    brand: "-Аудит",
    home: "/audit",
    // Подпись «Дела» — из макетов: пользователь ведёт дело о фирме-цели. Слой хранения
    // остаётся «субъектом» (audit_subjects, /api/v1/audit/subjects) — переименовывать его
    // ради подписи значило бы сломать зеркало модели и API без единой выгоды.
    nav: [
      ["/audit", "Дела"],
      ["/audit/group", "Группа"],
      ["/organization", "Организация"],
    ],
    // Канон хендоффа: Cube Hero (Audit) — accentColor ['#C77DFF','#7B3FE4'].
    cubeAccent: ["#C77DFF", "#7B3FE4"],   // фиолетовый неон
    // Разделы рейла по Экрану 6. Пункты будущих фаз («Реестр флагов», «Оценка»,
    // «Заключения») появятся вместе со своими экранами: ссылка в никуда хуже, чем
    // её отсутствие — она обещает то, чего нет.
    rail: [
      { title: "Работа", items: [["/audit", "Дела"], ["/audit/group", "Группа"]] },
      { title: "Организация", items: [["/organization", "Участники и тариф"]] },
    ],
  },
};

const KEY = "fe_product";

function stored(): Product {
  return localStorage.getItem(KEY) === "audit" ? "audit" : "business";
}

/**
 * Продукт по текущему маршруту. Разделы `/audit*` — аудит; `/projects*`, `/holdings*` —
 * бизнес-план; общие страницы (например, `/organization`) сохраняют последний выбранный
 * продукт (тема не «прыгает» на зелёную при переходе в общий раздел).
 */
export function productFromPath(pathname: string): Product {
  if (pathname === "/audit" || pathname.startsWith("/audit/")) return "audit";
  if (pathname.startsWith("/projects") || pathname.startsWith("/holdings")) return "business";
  return stored();
}

/** Проставить (или снять) data-product на <html> и запомнить выбор. Бизнес-план — дефолт. */
export function applyProduct(product: Product) {
  const root = document.documentElement;
  if (product === "audit") root.setAttribute("data-product", "audit");
  else root.removeAttribute("data-product");
  localStorage.setItem(KEY, product);
}
