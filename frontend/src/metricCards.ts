import type { MetricsOut, ValuationOut } from "./api/calc";
import { fmtMillions, fmtRatio, percent } from "./format";

/**
 * Карточки показателей эффективности: число, вердикт и тон.
 *
 * Вынесено из разметки результатов отдельным модулем, потому что здесь не оформление,
 * а **интерпретация**: знак NPV, сравнение доходности со ставкой, трактовка «не
 * определено». Ошибка тут не ломает вёрстку — она красит убыточный проект зелёным.
 *
 * Соглашение о тоне: зелёный ставится только когда вердикт **обоснован**. Если ставки
 * сравнения ещё нет (модель проекта не загрузилась), доходность остаётся нейтральной, а
 * не зелёной: иначе показатель успевал бы мигнуть «хорошо» и лишь потом покраснеть.
 */

export type Tone = "" | "good" | "bad" | "warn";

export interface MetricCard {
  label: string;
  value: string;
  sub: string;
  tone: Tone;
  hint: string;
}

/** Строка-Decimal → число; пусто/невалидно → null («не определён»). */
function dec(v: string | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
}

/** Вердикт доходности против ставки дисконтирования. */
function vsRate(value: number | null, rate: number | null, rateLabel: string,
                fallbackSub: string): { sub: string; tone: Tone } {
  if (value === null) return { sub: "Не определена", tone: "" };
  if (rate === null) return { sub: fallbackSub, tone: "" };
  return value >= rate
    ? { sub: `Выше ставки ${rateLabel}`, tone: "good" }
    : { sub: `Ниже ставки ${rateLabel}`, tone: "bad" };
}

/** Карточки эффективности проекта; ``discountRate`` — ставка сравнения (строка-Decimal). */
export function efficiencyCards(m: MetricsOut, discountRate?: string | null): MetricCard[] {
  const rate = dec(discountRate);
  const rateLabel = percent(discountRate, 0);
  const npv = dec(m.npv);
  const irr = vsRate(dec(m.irr_annual), rate, rateLabel, "Годовая доходность");
  const mirr = vsRate(dec(m.mirr_annual), rate, rateLabel, "Модифицированная IRR");
  const pi = dec(m.pi);

  return [
    {
      label: "NPV",
      value: fmtMillions(m.npv, { sign: true, digits: 1 }),
      sub: npv === null ? "Не определён"
        : npv > 0 ? "Создаёт стоимость" : npv < 0 ? "Разрушает стоимость" : "На грани",
      tone: npv === null ? "" : npv > 0 ? "good" : npv < 0 ? "bad" : "warn",
      hint: "Чистая приведённая стоимость — сумма дисконтированных денежных потоков. Положительная — проект создаёт стоимость.",
    },
    {
      label: "IRR",
      value: m.irr_annual != null ? percent(m.irr_annual, 1) : "—",
      ...irr,
      hint: "Внутренняя норма доходности — ставка, при которой NPV = 0. Сравнивается со ставкой дисконтирования.",
    },
    {
      label: "MIRR",
      value: m.mirr_annual != null ? percent(m.mirr_annual, 1) : "—",
      ...mirr,
      hint: "Модифицированная IRR: притоки реинвестируются по ставке дисконтирования — всегда один корень.",
    },
    {
      label: "ARR",
      value: m.arr_annual != null ? percent(m.arr_annual, 1) : "—",
      sub: m.arr_annual != null ? "Среднегодовая отдача" : "Нет инвестиций",
      tone: "",
      hint: "Средняя норма рентабельности: среднегодовые поступления к потребности в капитале.",
    },
    {
      label: "PI",
      value: pi !== null ? fmtRatio(m.pi, 2) : "—",
      sub: pi === null ? "—" : pi >= 1 ? "> 1 — эффективно" : "< 1 — неэффективно",
      tone: pi === null ? "" : pi >= 1 ? "good" : "bad",
      hint: "Индекс прибыльности — отношение дисконтированных притоков к вложениям.",
    },
    {
      label: "Срок окупаемости",
      value: m.pb_months != null ? `${m.pb_months} мес` : "> горизонта",
      sub: m.pb_months != null ? "В пределах горизонта" : "Не окупается",
      tone: m.pb_months != null ? "good" : "bad",
      hint: "Месяц, когда накопленный денежный поток становится положительным.",
    },
    {
      label: "Дисконт. окупаемость",
      value: m.dpb_months != null ? `${m.dpb_months} мес` : "—",
      // Не окупается по дисконтированному, но окупается по простому — «внимание»:
      // проект возвращает деньги, но не покрывает их стоимость во времени.
      sub: m.dpb_months != null ? "По дисконт. потоку" : "Не достигается",
      tone: m.dpb_months != null ? "good" : m.pb_months != null ? "warn" : "bad",
      hint: "То же по дисконтированному потоку — учитывает стоимость денег во времени.",
    },
    {
      label: "Потребность в финанс.",
      value: m.peak_financing_need ? fmtMillions(m.peak_financing_need, { digits: 1 }) : "—",
      sub: m.pv_investments
        ? `PV инвестиций ${fmtMillions(m.pv_investments, { digits: 1 })}`
        : "Максимальный дефицит",
      tone: "",
      hint: "Приведённая пиковая потребность в деньгах до выхода проекта в плюс.",
    },
  ];
}

export interface ValueCard { label: string; value: string; hint: string }

/** Карточки оценки стоимости бизнеса (без вердиктов — это оценки, а не приговор). */
export function valuationCards(v: ValuationOut): ValueCard[] {
  const money = (x: string | null | undefined) =>
    dec(x) !== null ? fmtMillions(x, { digits: 1 }) : "—";
  return [
    { label: "Чистые активы", value: fmtMillions(v.net_assets, { digits: 1 }),
      hint: "Активы минус обязательства на конец горизонта." },
    { label: "Модель Гордона", value: money(v.gordon_value),
      hint: "Капитализация бессрочного потока: CF·(1+g)/(r−g). Не считается при g ≥ ставки." },
    { label: "DDM", value: money(v.dividend_value),
      hint: "Капитализация дивидендов по модели Гордона." },
    { label: "По мультипликатору", value: money(v.earnings_multiple_value),
      hint: "Годовая чистая прибыль × заданный множитель (P/E-подход)." },
    { label: "Ликвидационная", value: money(v.liquidation_value),
      hint: "Возвратная стоимость активов при ликвидации минус обязательства." },
  ];
}

/** Карточки показателей во второй валюте (gap 1.4); пусто, если блок не считался. */
export function foreignCards(mf: MetricsOut | null | undefined, code: string,
                             rate?: string | null): ValueCard[] {
  if (!mf) return [];
  return [
    { label: "NPV", value: fmtMillions(mf.npv, { sign: true, digits: 1, unit: code }),
      hint: `Чистая приведённая стоимость во второй валюте (${code}) по ставке ${percent(rate, 0)}.` },
    { label: "IRR", value: mf.irr_annual != null ? percent(mf.irr_annual, 1) : "—",
      hint: "Внутренняя норма доходности потока во второй валюте (годовая)." },
    { label: "MIRR", value: mf.mirr_annual != null ? percent(mf.mirr_annual, 1) : "—",
      hint: "Модифицированная IRR потока во второй валюте." },
    { label: "PI", value: dec(mf.pi) !== null ? fmtRatio(mf.pi, 2) : "—",
      hint: "Индекс прибыльности во второй валюте." },
    { label: "Срок окупаемости", value: mf.pb_months != null ? `${mf.pb_months} мес` : "> горизонта",
      hint: "Месяц выхода накопленного потока (во второй валюте) в плюс." },
    { label: "Дисконт. окупаемость", value: mf.dpb_months != null ? `${mf.dpb_months} мес` : "—",
      hint: "То же по дисконтированному потоку во второй валюте." },
  ];
}
