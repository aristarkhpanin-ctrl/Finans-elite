import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { httpStatus } from "../../api/client";
import { useState } from "react";
import { checkout, getPlans, getSubscription, type Plan } from "../../api/org";
import { useToast } from "../../components/Toast";
import { Button, Modal, Skeleton } from "../../components/ui";

/** Цена тарифа. «По запросу» — не ноль: ноль на экране читается как «бесплатно». */
const price = (p: { price_rub: number; price_on_request: boolean }) =>
  p.price_on_request ? "По запросу" : p.price_rub === 0 ? "Бесплатно"
    : `${p.price_rub.toLocaleString("ru-RU")} ₽`;

/** Продукты платформы: тарифы у каждого свои, поэтому и экран тарифа переключается. */
const PRODUCTS: [string, string][] = [
  ["business", "Финанс-Элит"],
  ["audit", "Финанс-Аудит"],
];

/** Ключевые фичи плана по коду (для карточек). */
const PLAN_FEATURES: Record<string, string[]> = {
  free: ["4 отчёта + показатели", "Оценка бизнеса 5 методами", "Экспорт CSV/XLSX"],
  team: ["Всё из Free", "Холдинги и консолидация", "Анализ рисков"],
  business: ["Всё из Team", "Приоритетная поддержка", "Расширенные квоты"],
  audit_trial: ["Аналитическая форма и коэффициенты", "Диагностика и заключение",
                "Импорт и выгрузка XLSX"],
  audit_team: ["Всё из Пробного", "Группа компаний и консолидация", "Свои методики и нормативы"],
  audit_corp: ["Всё из Команды", "Без ограничений по делам и местам", "Индивидуальные условия"],
};

function QuotaBar({ label, used, max }: { label: string; used: number; max: number | null }) {
  const pct = max === null ? 0 : Math.min(100, Math.round((used / Math.max(max, 1)) * 100));
  const warn = max !== null && pct >= 80;
  return (
    <div>
      <div className="quota-item__top">
        <span className="quota-item__label">{label}</span>
        <span className="quota-item__val">
          {used} / {max ?? "∞"}
        </span>
      </div>
      <div className="quota-track">
        <div className={"quota-fill" + (warn ? " quota-fill--warn" : "")} style={{ width: max === null ? "8%" : `${pct}%` }} />
      </div>
      {warn && <div className="field-note" style={{ marginTop: 4, color: "var(--warn-text)" }}>Близко к лимиту тарифа</div>}
    </div>
  );
}

export function BillingTab({ orgId, canManage }: { orgId: string; canManage: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [target, setTarget] = useState<Plan | null>(null);
  const [product, setProduct] = useState("business");

  const sub = useQuery({ queryKey: ["subscription", orgId, product],
                         queryFn: () => getSubscription(orgId, product) });
  const plans = useQuery({ queryKey: ["plans", product], queryFn: () => getPlans(product) });

  const change = useMutation({
    mutationFn: (code: string) => checkout(orgId, code),
    onSuccess: (res) => {
      setTarget(null);
      if (res.confirmation_url) {
        window.location.assign(res.confirmation_url); // оплата ЮKassa
      } else {
        qc.invalidateQueries({ queryKey: ["subscription", orgId] });
        toast("Тариф изменён", { kind: "success" });
      }
    },
    onError: (e: unknown) =>
      toast(httpStatus(e) === 403 ? "Нужны права владельца" : "Не удалось сменить тариф", { kind: "error" }),
  });

  if (sub.isLoading || plans.isLoading) {
    return (
      <div>
        <Skeleton height={120} style={{ borderRadius: 14, marginBottom: 20 }} />
        <div className="plan-grid">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} height={220} style={{ borderRadius: 14 }} />
          ))}
        </div>
      </div>
    );
  }
  if (sub.isError || !sub.data) {
    return (
      <div className="error-state">
        <div className="error-state__ico">!</div>
        <div className="error-state__title">Не удалось загрузить тариф</div>
        <Button onClick={() => sub.refetch()}>Повторить</Button>
      </div>
    );
  }

  const s = sub.data;
  const currentPlan = plans.data?.find((p) => p.code === s.plan_code);

  return (
    <div>
      {/* Продукты продаются порознь, поэтому и тариф у каждого свой: общий экран
          означал бы, что покупка «Аудита» меняет условия по «Элит». */}
      <div className="case-filters" role="group" aria-label="Продукт">
        {PRODUCTS.map(([key, label]) => (
          <button key={key} type="button" aria-pressed={product === key}
                  className={"case-filter" + (product === key ? " case-filter--active" : "")}
                  onClick={() => { setProduct(key); setTarget(null); }}>
            {label}
          </button>
        ))}
      </div>

      <div className="billing-grid">
        <div className="plan-current">
          <div className="plan-current__label">Текущий тариф</div>
          <div className="plan-current__name">
            {s.plan_name}
            <span className="plan-active-dot" title="Активна" />
          </div>
          <div className="plan-current__price">
            {currentPlan ? price(currentPlan) : "—"}
            {currentPlan && !currentPlan.price_on_request && currentPlan.price_rub > 0 &&
              <span style={{ color: "var(--subtle)", fontWeight: 500 }}> / мес</span>}
          </div>
          {s.current_period_end && (
            <div className="plan-current__note">
              Продление {new Date(s.current_period_end).toLocaleDateString("ru-RU")}
            </div>
          )}
        </div>

        <div className="quota-card">
          {/* Подпись берётся из тарифа: у «Элит» это проекты, у «Аудита» — дела. */}
          <QuotaBar label={s.unit_name === "дел" ? "Дела" : "Проекты"}
                    used={s.used_units} max={s.max_units ?? null} />
          <QuotaBar label="Участники" used={s.used_members} max={s.max_members ?? null} />
        </div>
      </div>

      <div className="terms-head">Тарифные планы</div>
      {plans.data && (
        <div className="plan-grid">
          {plans.data.map((p) => {
            const current = p.code === s.plan_code;
            return (
              <div key={p.code} className={"plan-card" + (current ? " plan-card--current" : "")}>
                {current && <span className="plan-ribbon">Текущий</span>}
                <div className="plan-card__name">{p.name}</div>
                <div className="plan-card__price">
                  {price(p)}
                  {!p.price_on_request && p.price_rub > 0 && <small> / мес</small>}
                </div>
                <div className="plan-card__limits">
                  ▢ {p.max_units ?? "∞"} {p.unit_name} · ○ {p.max_members ?? "∞"} участников
                </div>
                <div className="plan-feats">
                  {(PLAN_FEATURES[p.code] ?? []).map((f) => (
                    <div className="plan-feat" key={f}>
                      <span className="plan-feat__check">✓</span>
                      {f}
                    </div>
                  ))}
                </div>
                {current ? (
                  <Button variant="ghost" disabled>
                    Текущий тариф
                  </Button>
                ) : (
                  <Button disabled={!canManage} onClick={() => setTarget(p)}>
                    Перейти
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}
      {!canManage && (
        <p className="muted" style={{ marginTop: 12 }}>
          🔒 Смена тарифа доступна только владельцу организации.
        </p>
      )}

      {/* Модал смены тарифа */}
      <Modal
        open={!!target}
        onClose={() => !change.isPending && setTarget(null)}
        title="Смена тарифа"
        maxWidth={440}
        actions={
          <>
            <Button variant="ghost" disabled={change.isPending} onClick={() => setTarget(null)}>
              Отмена
            </Button>
            <Button loading={change.isPending} onClick={() => target && change.mutate(target.code)}>
              Подтвердить
            </Button>
          </>
        }
      >
        {target && (
          <>
            <div className="plan-diff">
              <div className="plan-diff__box">
                <div className="plan-diff__label">Сейчас</div>
                <div className="plan-diff__val">{s.plan_name}</div>
              </div>
              <span className="plan-diff__arrow">→</span>
              <div className="plan-diff__box" style={{ background: "var(--primary-soft)" }}>
                <div className="plan-diff__label">Новый</div>
                <div className="plan-diff__val">{target.name}</div>
              </div>
            </div>
            <div className="modal__sub" style={{ margin: 0 }}>
              Стоимость нового тарифа — <b style={{ color: "var(--text)" }}>
                {price(target)}{!target.price_on_request && target.price_rub > 0 ? " / мес" : ""}</b>.
              {target.price_on_request
                ? " Условия обсуждаются отдельно — мы свяжемся с вами после заявки."
                : target.price_rub > 0
                  ? " После подтверждения откроется страница оплаты."
                  : " Тариф активируется сразу."}
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}
