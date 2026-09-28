import { useQuery } from "@tanstack/react-query";
import { getOverview, type ProductState } from "../../api/org";
import { ErrorState, Loading } from "../../components/ui";
import { plural } from "../../format";

/**
 * Организация одним взглядом (ADMIN-PHASE-F, F7).
 *
 * Ответы на «сколько у нас проектов и дел, сколько ещё можно завести, когда кончается
 * тариф» были разложены по трём экранам и по отказам, которые приходили уже в момент
 * сохранения. Здесь они собраны — и собраны **на сервере, из существующего**: второй
 * источник любого из этих чисел однажды разошёлся бы с первым.
 *
 * Правила пустоты приходят вместе с числами и не переписываются здесь своими словами:
 * `null` у предела — «без предела», а не ноль; дата последнего расчёта вместо их числа;
 * `notes` показываются целиком.
 */

function when(iso: string | null | undefined, dash = "—"): string {
  if (!iso) return dash;
  return new Date(iso).toLocaleDateString("ru-RU",
    { day: "numeric", month: "long", year: "numeric" });
}

/** Статус подписки словами. `none` — «не оформляли», а не «бесплатный тариф». */
const STATUS: Record<string, string> = {
  active: "действует",
  trialing: "пробный период",
  past_due: "просрочена оплата",
  canceled: "отменена",
  none: "подписку не оформляли",
};

/**
 * «Осталось» человеческим языком. `null` — предела нет вовсе, и это **не ноль**:
 * написать здесь «0» значило бы показать корпоративному клиенту, что ему ничего нельзя.
 */
function left(limit: number | null | undefined, leftN: number | null | undefined,
              unit: string): string {
  if (limit === null || limit === undefined) return "без предела";
  return `осталось ${leftN ?? 0} из ${limit} ${unit}`;
}

function ProductCard({ p }: { p: ProductState }) {
  return (
    <div className="audit-block">
      <div className="audit-block__title">{p.product_name}</div>
      <div className="page-sub" style={{ marginTop: 0 }}>
        Тариф «{p.plan_name}» · {STATUS[p.status] ?? p.status}
      </div>

      <div className="sess-list" style={{ marginTop: 10 }}>
        <div className="sess-row">
          <div style={{ minWidth: 0 }}>
            <div className="sess-row__device">
              {p.units_used} {p.unit_name}
            </div>
            <div className="sess-row__meta">{left(p.units_limit, p.units_left, p.unit_name)}</div>
          </div>
        </div>
        <div className="sess-row">
          <div style={{ minWidth: 0 }}>
            <div className="sess-row__device">Участники</div>
            <div className="sess-row__meta">
              {left(p.members_limit, p.members_left, "мест")}
            </div>
          </div>
        </div>
        <div className="sess-row">
          <div style={{ minWidth: 0 }}>
            <div className="sess-row__device">Оплачено</div>
            <div className="sess-row__meta">
              {/* Пусто — «не истекает», а не «истёк давно». */}
              {p.period_end
                ? `до ${when(p.period_end)}` + (p.days_left !== null && p.days_left !== undefined
                    ? ` · ${p.days_left} ${plural(p.days_left, "день", "дня", "дней")}`
                    : "")
                : "тариф не истекает"}
            </div>
          </div>
        </div>
      </div>

      {/* Ограничение — теми же словами, какими отказывает сохранение. Предупреждение
          (льготный срок) идёт тем же каналом и отличается полем, а не догадкой. */}
      {p.restriction_reason && (
        <div className={"restr " + (p.restriction_blocking ? "restr--suspended" : "")}
             role="status" style={{ marginTop: 12 }}>
          <span className="restr__ico" aria-hidden="true">
            {p.restriction_blocking ? "⛔" : "⏳"}
          </span>
          <div>
            <div className="restr__title">
              {p.restriction_blocking ? "Изменения закрыты" : "Льготный срок"}
              {p.grace_left !== null && p.grace_left !== undefined
                && ` — ${p.grace_left} ${plural(p.grace_left, "день", "дня", "дней")}`}
            </div>
            <div className="restr__text">
              {p.restriction_reason} {p.restriction_remedy}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function OverviewTab({ orgId }: { orgId: string }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["org-overview", orgId],
    queryFn: () => getOverview(orgId),
  });

  if (isLoading) return <Loading />;
  if (isError || !data) return <ErrorState text="Не удалось собрать сводку"
                                           onRetry={() => refetch()} />;

  return (
    <div style={{ display: "grid", gap: 18, maxWidth: 860 }}>
      <div className="audit-block">
        <div className="audit-block__title">Что заведено</div>
        <div className="log-list" role="table" aria-label="Объёмы организации">
          <div className="log-row adm-row adm-row--head" role="row">
            <div role="columnheader">Проекты</div>
            <div role="columnheader">Дела</div>
            <div role="columnheader">Участники</div>
            <div role="columnheader">Последний расчёт</div>
          </div>
          <div className="log-row adm-row" role="row">
            <div role="rowheader">{data.projects}</div>
            <div role="cell">
              {data.cases}
              {data.groups > 0 && <span className="adm-sub">групп: {data.groups}</span>}
            </div>
            <div role="cell">
              {data.members}
              {data.members_blocked > 0
                && <span className="adm-sub">приостановлено: {data.members_blocked}</span>}
            </div>
            {/* Числа расчётов у платформы нет — показывается дата последнего. */}
            <div role="cell">{when(data.last_calculated_at, "ещё не считали")}</div>
          </div>
        </div>
      </div>

      {data.products.map((p) => <ProductCard p={p} key={p.product} />)}

      {/* Оговорки — часть ответа, а не украшение: без них «осталось 0» и «без предела»
          выглядят одинаково, а «неизвестно» читается как «не работает». */}
      <ul className="mnotes">
        {data.notes.map((n) => <li key={n}>{n}</li>)}
      </ul>
    </div>
  );
}
