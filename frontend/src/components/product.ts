// Продукт платформы: «Финанс-Элит» (бизнес-план) и «Финанс-Аудит» (анализ факта).
// Активный продукт задаёт тему через атрибут data-product на <html> (см. styles.css:
// набор фиолетовых токенов для data-product="audit"). Определяется по маршруту.

export type Product = "business" | "audit";

export interface ProductMeta {
  id: Product;
  brand: string;        // слово в шапке после «Финанс»
  home: string;         // корневой маршрут продукта
  nav: readonly (readonly [string, string])[];
  cubeAccent: [string, string];   // акценты куб-марки [яркий, глубокий] под тему продукта
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
    nav: [
      ["/audit", "Субъекты"],
      ["/audit/group", "Группа"],
      ["/organization", "Организация"],
    ],
    // Канон хендоффа: Cube Hero (Audit) — accentColor ['#C77DFF','#7B3FE4'].
    cubeAccent: ["#C77DFF", "#7B3FE4"],   // фиолетовый неон
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
