/**
 * Абонентская база: приток и отток (зеркало SPEC §5).
 *
 * Это **предпросмотр редактора**, а не источник чисел. Расчётную базу возвращает сервер
 * (`subscription_base` в ответе расчёта), и на экране результатов показана именно она;
 * здесь она нужна там, где сервер спросить ещё не о чем — пока пользователь набирает
 * приток и отток и не видит, во что они складываются. Без предпросмотра «70 новых при
 * оттоке 3%» остаётся загадкой до первого расчёта, а это как раз то место, где ошибаются.
 *
 * Рекуррента одна и целиком помещается в одну строку, поэтому отдельной фикстуры-эталона
 * у зеркала нет (в отличие от сметы календаря, где правил десятки): её держат unit-тесты
 * **на тех же числах**, что и питоновские — `tests/test_subscription.py`.
 */

/** Число из строки ввода: пусто, мусор и запятая-десятичная не должны рушить предпросмотр. */
function num(v: string | undefined): number {
  if (!v) return 0;
  const parsed = Number(String(v).replace(/\s| | /g, "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

export interface SubscriptionInput {
  starting_base: string;
  new_per_month: string[];
  churn_monthly: string;
}

export interface SubscriptionPreview {
  /** Действующая база на конец месяца = объём продаж. */
  base: number[];
  /** Выбытие за месяц (от базы начала месяца, **до** притока). */
  churned: number[];
  /**
   * Потолок базы = приток / отток, если приток постоянен. `null` — при нулевом оттоке
   * (потолка нет, база растёт вечно) или непостоянном притоке (одного потолка не
   * существует, и назвать какой-то из них значило бы придумать число).
   */
  ceiling: number | null;
}

/**
 * `база[t] = база[t−1] · (1 − отток) + новые[t]`, `база[−1] = starting_base`.
 *
 * Отток берётся от базы **начала месяца, до притока**: пришедший в этом месяце абонент в
 * этом же месяце не уходит. Ряд притока короче горизонта — дальше приток нулевой, а не
 * «повторить последнее»: домыслить его значило бы дорисовать продажи, которых не
 * закладывали. Старт продукта (`startMonth`) гейтит приток, а не выведенную базу — иначе
 * абоненты копились бы до старта и вываливались одним скачком.
 */
export function subscriptionPreview(
  sub: SubscriptionInput, n: number, startMonth = 0,
): SubscriptionPreview {
  const churn = num(sub.churn_monthly);
  const start = Math.max(0, startMonth);
  const base: number[] = [];
  const churned: number[] = [];
  let prev = start > 0 ? 0 : num(sub.starting_base);
  for (let t = 0; t < n; t++) {
    const left = prev * churn;
    const arrived = t >= start ? num(sub.new_per_month[t]) : 0;
    churned.push(left);
    prev = prev - left + arrived;
    base.push(prev);
  }
  const arrivals = Array.from({ length: n }, (_, t) => (t >= start ? num(sub.new_per_month[t]) : 0))
    .slice(start);
  const constant = arrivals.length > 0 && arrivals.every((v) => v === arrivals[0]);
  return {
    base,
    churned,
    ceiling: churn > 0 && constant ? arrivals[0] / churn : null,
  };
}
