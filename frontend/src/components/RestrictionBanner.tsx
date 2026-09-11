import type { OrganizationMembership } from "../api/types";
import type { Product } from "./product";

/**
 * Баннер режима чтения и выгрузки (ADMIN-DECOMPOSITION.md, B2).
 *
 * Ограниченная организация видит свои модели, считает их и выгружает документы, но не
 * заводит новые и не правит старые. Без баннера это выглядит как поломка: кнопки на
 * месте, нажатие ничего не даёт — и клиент идёт не в поддержку, а в отзывы.
 *
 * **Причина берётся с сервера, а не сочиняется здесь.** Тот же `access.restriction_for`,
 * который отказывает на записи, называет и причину: второй источник этой правды однажды
 * разошёлся бы с первым, и на экране висело бы объяснение отказа, которого уже нет.
 *
 * Баннер показывается **по активному продукту**: подписка своя у каждого, и
 * просроченный «Аудит» не повод пугать того, кто открыл оплаченный «Элит». Ручная
 * приостановка приходит по обоим продуктам — она про организацию целиком.
 *
 * Кнопки при этом **не прячутся**. Спрятанная кнопка не защита (отказ всё равно выносит
 * сервер), зато она превращает понятное «нельзя, потому что…» в необъяснимое исчезновение
 * половины интерфейса.
 */
export function RestrictionBanner({ org, product }: {
  org: OrganizationMembership | undefined;
  product: Product;
}) {
  const restriction = (org?.restrictions ?? []).find((r) => r.product === product);
  if (!restriction) return null;

  return (
    <div className={"restr restr--" + restriction.kind} role="status">
      <span className="restr__ico" aria-hidden="true">
        {restriction.kind === "suspended" ? "⏸" : "₽"}
      </span>
      <div>
        <div className="restr__title">
          {restriction.kind === "suspended"
            ? "Организация приостановлена"
            : "Режим чтения и выгрузки"}
        </div>
        <div className="restr__text">
          {restriction.reason} {restriction.remedy}
        </div>
      </div>
    </div>
  );
}
