import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getPlans, type Plan } from "../api/org";
import { PublicLayout } from "../components/PublicLayout";
import { PRODUCTS, type Product } from "../components/product";
import { ErrorState, Loading } from "../components/ui";
import { usePageTitle } from "../pageTitle";
import { gift, price, quota, rub } from "../planText";

/**
 * Тарифы (пакет L, L5) — публично, из того же каталога, по которому платформа выставляет
 * счета (`/api/v1/plans`): цена на сайте и цена в оплате — одно число. Цену года считает
 * сервер; экран только называет подарок.
 */
export function PricingPage() {
  usePageTitle("Тарифы");
  const query = useQuery({ queryKey: ["plans", "all"], queryFn: () => getPlans() });

  return (
    <PublicLayout>
      <h1>Тарифы</h1>
      <p className="page-sub">
        Цены — за месяц. Продукты оплачиваются порознь: у организации своя подписка на
        каждый. Порядок оплаты и продления — в <Link to="/legal/offer">оферте</Link>.
      </p>
      {query.isLoading && <Loading text="Загружаем тарифы…" />}
      {query.isError && <ErrorState text="Тарифы не загрузились" onRetry={() => void query.refetch()} />}
      {query.data && (["business", "audit"] as Product[]).map((product) => {
        const plans = query.data.filter((p) => p.product === product);
        if (plans.length === 0) return null;
        return (
          <section key={product} aria-labelledby={`plans-${product}`}>
            <h2 id={`plans-${product}`} className="rsection-label">
              Финанс{PRODUCTS[product].brand}
            </h2>
            <div className="pub-plans">
              {plans.map((plan) => <PlanCard key={plan.code} plan={plan} />)}
            </div>
          </section>
        );
      })}
    </PublicLayout>
  );
}

function PlanCard({ plan }: { plan: Plan }) {
  const annual = plan.annual_price_rub ?? null;
  const free = plan.annual_free_months ?? 0;
  return (
    <div className="pub-plan">
      <div className="pub-plan__name">{plan.name}</div>
      <div className="pub-plan__price">
        {price(plan)}
        {!plan.price_on_request && plan.price_rub > 0 && <span> в месяц</span>}
      </div>
      {annual != null && (
        <div className="pub-plan__annual">
          Год — {rub(annual)}{free > 0 && ` (${gift(free)})`}
        </div>
      )}
      <div className="pub-plan__quota">{quota(plan)}</div>
      {plan.price_on_request && (
        <div className="pub-plan__note">
          Условия обсуждаются отдельно — контакты в разделе{" "}
          <Link to="/legal/requisites">«Реквизиты»</Link>.
        </div>
      )}
    </div>
  );
}
