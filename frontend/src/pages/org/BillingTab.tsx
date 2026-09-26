import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { httpDetail, httpStatus } from "../../api/client";
import { useState } from "react";
import { changePlan, checkout, disableAutoRenew, getPlans, getQuote, getSubscription,
         type CheckoutQuote, type Plan, type Subscription } from "../../api/org";
import { useToast } from "../../components/Toast";
import { Button, Modal, Skeleton } from "../../components/ui";

/** Сумма в рублях: «2 900 ₽». */
const rub = (n: number) => `${n.toLocaleString("ru-RU")} ₽`;

/** Цена тарифа. «По запросу» — не ноль: ноль на экране читается как «бесплатно». */
const price = (p: { price_rub: number; price_on_request: boolean }) =>
  p.price_on_request ? "По запросу" : p.price_rub === 0 ? "Бесплатно" : rub(p.price_rub);

/** Платный тариф оплачивается в продукте (а не назначается платформой и не бесплатен). */
const payable = (p: Plan) => p.price_rub > 0 && !p.price_on_request;

const day = (iso: string) => new Date(iso).toLocaleDateString("ru-RU");

/**
 * Автопродление на карточке текущего тарифа (G5): что спишут, когда и откуда — и почему
 * не прошло, если не прошло. Причина приходит с сервера словами и показывается как есть:
 * выключенное не рукой клиента автопродление, о котором молчит экран, клиент обнаружил
 * бы по закрытой записи.
 */
function AutoRenewNote({ s }: { s: Subscription }) {
  return (
    <>
      {s.auto_renew && (
        <div className="plan-current__note">
          Автопродление: {rub(s.renew_amount_rub ?? 0)} за {s.renew_months} мес.
          с «{s.payment_method_title}»
          {s.next_charge_at && <>, не раньше {day(s.next_charge_at)}</>}.
          Письмо о списании приходит за неделю.
        </div>
      )}
      {s.renew_error && (
        <div className="field-note field-note--warn" style={{ marginTop: 6 }}>
          {s.renew_error}
        </div>
      )}
    </>
  );
}

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
  // Срок и согласие выбираются в окне оплаты и сбрасываются при каждом открытии: отметка
  // согласия, оставшаяся от прошлого окна, была бы согласием, которого не давали.
  const [months, setMonths] = useState(1);
  const [autoRenew, setAutoRenew] = useState(false);
  const [confirmOff, setConfirmOff] = useState(false);

  const open = (p: Plan) => { setTarget(p); setMonths(1); setAutoRenew(false); };

  const sub = useQuery({ queryKey: ["subscription", orgId, product],
                         queryFn: () => getSubscription(orgId, product) });
  const plans = useQuery({ queryKey: ["plans", product], queryFn: () => getPlans(product) });
  /** Сумма и срок — с сервера, теми же функциями, что и оплата: своей копии правила
   *  «продление продолжает период» у экрана нет. */
  const quote = useQuery({
    queryKey: ["quote", orgId, target?.code, months],
    queryFn: () => getQuote(orgId, target!.code, months),
    enabled: !!target && payable(target),
  });

  const turnOff = useMutation({
    mutationFn: () => disableAutoRenew(orgId, product),
    onSuccess: () => {
      setConfirmOff(false);
      qc.invalidateQueries({ queryKey: ["subscription", orgId] });
      toast("Автопродление выключено", { kind: "success" });
    },
    onError: (e: unknown) =>
      toast(httpDetail(e) ?? "Не удалось выключить автопродление", { kind: "error" }),
  });

  /**
   * Две дороги, и они не взаимозаменяемы (F1).
   *
   * **Платный тариф включает оплата** — раньше экран звал её для любого тарифа, и
   * понижение на бесплатный уходило платежом на ноль рублей: ручной провайдер включал
   * его молча, а ЮKassa получила бы бессмыслицу. Понижение идёт своим маршрутом, и он
   * же **стирает** чужой срок.
   *
   * Тариф «по запросу» не берётся ни одной из дорог: его условия согласуют вне
   * продукта. Кнопки у него нет вовсе — см. карточку тарифа.
   */
  const change = useMutation({
    mutationFn: (plan: Plan) =>
      payable(plan)
        ? checkout(orgId, plan.code, { months, autoRenew })
        : changePlan(orgId, plan.code).then(
            () => ({ activated: true, confirmation_url: null })),
    onSuccess: (res) => {
      setTarget(null);
      if (res.confirmation_url) {
        window.location.assign(res.confirmation_url); // оплата ЮKassa
      } else {
        qc.invalidateQueries({ queryKey: ["subscription", orgId] });
        toast("Тариф изменён", { kind: "success" });
      }
    },
    // Отказ сервера называет причину и выход (например, «оплата не подключена —
    // оплатите по счёту»). Общее «не удалось» съело бы ровно то, что клиенту нужно.
    onError: (e: unknown) =>
      toast(httpStatus(e) === 403 ? "Нужны права владельца"
              : httpDetail(e) ?? "Не удалось сменить тариф", { kind: "error" }),
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
          {/* «Продление» без автопродления обещало бы списание, которого не будет:
              дата — это конец оплаченного, и названа она так. */}
          {s.current_period_end && (
            <div className="plan-current__note">
              Оплачено до {day(s.current_period_end)}
            </div>
          )}
          <AutoRenewNote s={s} />
          {s.auto_renew && canManage && (
            <Button variant="ghost" style={{ marginTop: 10 }}
                    onClick={() => setConfirmOff(true)}>
              Выключить автопродление
            </Button>
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
                ) : p.price_on_request ? (
                  /* Кнопки здесь нет намеренно (F1): условия согласуют вне продукта, а
                     автоматической заявки платформа не отправляет — ящика для входящих
                     писем у неё нет. Кнопка «Запросить», после которой ничего не
                     происходит, хуже её отсутствия. */
                  <div className="field-note">
                    Условия согласуются отдельно — тариф назначает платформа.
                    Напишите нам: заявку этот экран не отправляет.
                  </div>
                ) : (
                  <Button disabled={!canManage} onClick={() => open(p)}>
                    {p.price_rub > 0 ? "Перейти" : "Перейти на бесплатный"}
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
            <Button loading={change.isPending} onClick={() => target && change.mutate(target)}>
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
            {payable(target) ? (
              <PayTerms plan={target} current={s} months={months} setMonths={setMonths}
                        autoRenew={autoRenew} setAutoRenew={setAutoRenew}
                        quote={quote.data} quoteFailed={quote.isError} />
            ) : (
              <div className="modal__sub" style={{ margin: 0 }}>
                Стоимость нового тарифа — <b style={{ color: "var(--text)" }}>{price(target)}</b>.
                {" Тариф сменится сразу. Квота станет меньше: то, что уже заведено, "
                  + "останется на месте, а новое можно будет добавлять в пределах "
                  + "бесплатного тарифа."}
                {s.auto_renew && " Автопродление выключится, сохранённый способ оплаты будет забыт."}
              </div>
            )}
          </>
        )}
      </Modal>

      {/* Выключение автопродления: последствия — до нажатия. */}
      <Modal
        open={confirmOff}
        onClose={() => !turnOff.isPending && setConfirmOff(false)}
        title="Выключить автопродление?"
        maxWidth={440}
        actions={
          <>
            <Button variant="ghost" disabled={turnOff.isPending}
                    onClick={() => setConfirmOff(false)}>
              Оставить
            </Button>
            <Button loading={turnOff.isPending} onClick={() => turnOff.mutate()}>
              Выключить
            </Button>
          </>
        }
      >
        <div className="modal__sub" style={{ margin: 0 }}>
          Больше ничего не будет списано, и период просто закончится
          {s.current_period_end ? ` ${day(s.current_period_end)}` : ""}. Сохранённый способ
          оплаты будет забыт: включить автопродление снова можно только новой оплатой с
          отметкой согласия.
        </div>
      </Modal>
    </div>
  );
}

/**
 * Условия оплаты в окне: срок, сумма, до какого дня будет оплачено и согласие (G5).
 *
 * **Согласие — отдельная отметка, и выключена по умолчанию**: деньги клиента не
 * списываются без его явного решения. Отметка называет сумму и срок, на которые оно
 * даётся, и что будет до списания (письмо за неделю). Где автопродление невозможно
 * (нет оплаты в продукте или почты), отметка не прячется, а стоит выключенной с
 * причиной: исчезнувшая функция читается как «здесь такого нет», а она есть.
 */
function PayTerms({ plan, current, months, setMonths, autoRenew, setAutoRenew, quote,
                    quoteFailed }: {
  plan: Plan;
  current: Subscription;
  months: number;
  setMonths: (m: number) => void;
  autoRenew: boolean;
  setAutoRenew: (v: boolean) => void;
  quote: CheckoutQuote | undefined;
  quoteFailed: boolean;
}) {
  const annual = plan.annual_price_rub ?? null;
  const amount = quote?.amount_rub ?? (months === 12 && annual !== null ? annual
                                                                           : plan.price_rub);
  return (
    <div className="pay-terms">
      <div className="seg" role="group" aria-label="Срок оплаты">
        <button type="button" aria-pressed={months === 1}
                className={"seg__btn" + (months === 1 ? " seg__btn--active" : "")}
                onClick={() => setMonths(1)}>
          Месяц · {rub(plan.price_rub)}
        </button>
        {annual !== null && (
          <button type="button" aria-pressed={months === 12}
                  className={"seg__btn" + (months === 12 ? " seg__btn--active" : "")}
                  onClick={() => setMonths(12)}>
            Год · {rub(annual)}
            {(plan.annual_discount_percent ?? 0) > 0 && ` (−${plan.annual_discount_percent} %)`}
          </button>
        )}
      </div>
      <div className="field-note" style={{ marginTop: 6 }}>
        Месяц — 30 дней, год — 12 таких периодов.
      </div>

      <div className="pay-terms__sum">
        К оплате: <b>{rub(amount)}</b>
        {quote && quote.discount_percent > 0 &&
          <> вместо {rub(quote.full_price_rub)} — скидка {quote.discount_percent} %</>}
      </div>
      {quote?.ends_at && (
        <div className="field-note">
          Будет оплачено до {day(quote.ends_at)}
          {quote.continues && " — период продолжится от конца текущего, дни не теряются"}.
        </div>
      )}
      {quote && quote.lost_days > 0 && (
        <div className="field-note field-note--warn">
          Оставшиеся {quote.lost_days} дн. тарифа «{current.plan_name}» не переносятся:
          новый тариф начнёт свой период с оплаты.
        </div>
      )}
      {quoteFailed && (
        <div className="field-note field-note--warn">
          Не удалось рассчитать срок заранее — сумму и дату назовёт страница оплаты.
        </div>
      )}

      <label className="pay-terms__consent">
        <input type="checkbox" checked={autoRenew}
               disabled={!current.auto_renew_available}
               onChange={(e) => setAutoRenew(e.target.checked)} />
        <span>
          Продлевать автоматически: списывать {rub(amount)} каждые {months} мес. с
          сохранённого способа оплаты. Письмо о списании придёт за неделю, выключить
          можно в любой момент.
        </span>
      </label>
      {!current.auto_renew_available && (
        <div className="field-note">{current.auto_renew_unavailable_reason}</div>
      )}
      <div className="field-note" style={{ marginTop: 10 }}>
        После подтверждения откроется страница оплаты.
      </div>
    </div>
  );
}
