import { line, type CalcResponse } from "../api/calc";
import { fmtMillions, fmtRatio, percent } from "../format";
import { CubeHero } from "./CubeHero";

type Status = "good" | "warn" | "bad" | "neutral";

interface Verdict {
  title: string;
  value: string;
  message: string;
  sub: string;
  status: Status;
}

const BADGE: Record<Status, string> = {
  good: "✓ хорошо",
  warn: "внимание",
  bad: "риск",
  neutral: "инфо",
};

const last = (a: number[]) => (a.length ? a[a.length - 1] : 0);

/**
 * Сводка-вердикт (макет «Этап 12»): 9 карточек со статус-полосой,
 * бейджем, значением mono и выводом; первая — с куб-акцентом при good.
 */
export function SummaryView({ result, discountRate }: { result: CalcResponse; discountRate?: string }) {
  const m = result.metrics;
  const cash = line(result.balance, "B1").map(Number);
  const minCash = cash.length ? Math.min(...cash) : 0;
  const minCashMonth = cash.indexOf(minCash) + 1;
  const retained = last(line(result.balance, "B32").map(Number));
  const b8 = last(line(result.balance, "B8").map(Number));
  const b25 = last(line(result.balance, "B25").map(Number));
  const currentRatio = b25 > 0 ? b8 / b25 : null;
  const npv = Number(m.npv);
  const ratePct = discountRate ? percent(discountRate, 1) : null;
  const irr = m.irr_annual !== null && m.irr_annual !== undefined ? Number(m.irr_annual) : null;
  const rate = discountRate ? Number(discountRate) : null;

  const verdicts: Verdict[] = [
    {
      title: "Чистая приведённая стоимость (NPV)",
      value: fmtMillions(m.npv, { sign: true, digits: 1 }),
      message: npv > 0 ? "Проект создаёт стоимость" : npv < 0 ? "Проект разрушает стоимость" : "На грани окупаемости",
      sub:
        npv > 0
          ? `При ставке ${ratePct ?? "дисконтирования"} притоки превышают оттоки`
          : `При ставке ${ratePct ?? "дисконтирования"} дисконтированные оттоки превышают притоки`,
      status: npv > 0 ? "good" : npv < 0 ? "bad" : "warn",
    },
    {
      title: "Внутренняя норма доходности (IRR)",
      value: irr !== null ? percent(m.irr_annual, 1) : "—",
      message:
        irr === null
          ? "Не определена"
          : rate !== null
            ? irr >= rate
              ? `Выше стоимости капитала (${ratePct})`
              : `Ниже стоимости капитала (${ratePct})`
            : "Годовая доходность проекта",
      sub:
        irr === null
          ? "Нет смены знака денежного потока"
          : rate !== null && irr < rate
            ? "Проект не покрывает требуемую доходность"
            : "Доходность выше требуемой",
      status: irr === null ? "neutral" : rate === null || irr >= rate ? "good" : "bad",
    },
    {
      title: "Индекс прибыльности (PI)",
      value: m.pi ? fmtRatio(m.pi, 2) : "—",
      message: m.pi == null ? "Не определён" : `Каждый ₽ вложений возвращает ${fmtRatio(m.pi, 2)} ₽`,
      sub: m.pi == null ? "" : Number(m.pi) >= 1 ? "Больше 1 — эффективно" : "Меньше 1 — вложения не окупаются",
      status: m.pi == null ? "neutral" : Number(m.pi) >= 1 ? "good" : "bad",
    },
    {
      title: "Срок окупаемости",
      value: m.pb_months != null ? `${m.pb_months} мес` : "Не окупается",
      message:
        m.pb_months != null
          ? m.dpb_months != null
            ? `Дисконтированный — ${m.dpb_months} мес`
            : "Дисконтированный — за горизонтом"
          : "Накопленный поток не выходит в плюс",
      sub: "В пределах горизонта планирования",
      status: m.pb_months != null ? "good" : "bad",
    },
    {
      title: "Минимальный остаток денег",
      value: fmtMillions(String(minCash), { sign: true, digits: 1 }),
      message: minCash < 0 ? "Кассовый разрыв — требуется финансирование" : "Кассовых разрывов нет",
      sub:
        minCash < 0
          ? `Период ${minCashMonth}: денег недостаточно для платежей`
          : `Минимум — в периоде ${minCashMonth}`,
      status: minCash < 0 ? "bad" : "good",
    },
    {
      title: "Потребность в финансировании",
      value: m.peak_financing_need ? fmtMillions(m.peak_financing_need, { digits: 1 }) : "—",
      message: minCash < 0 ? "Привлеките кредитную линию" : "Максимальный накопленный дефицит",
      sub: minCash < 0 ? "Включите автоподбор финансирования" : "Приведённый дефицит до выхода в плюс",
      status: minCash < 0 ? "bad" : "neutral",
    },
    {
      title: "Текущая ликвидность",
      value: currentRatio != null ? fmtRatio(currentRatio, 1) : "—",
      message:
        currentRatio == null
          ? "Нет краткосрочных обязательств"
          : currentRatio >= 1.5
            ? "Устойчивое покрытие"
            : currentRatio >= 1
              ? "На грани нормы"
              : "Ниже нормы",
      sub:
        currentRatio == null
          ? ""
          : currentRatio >= 1
            ? "Норма ≥ 1,5 — устойчиво"
            : "Краткосрочные обязательства не покрыты",
      status: currentRatio == null ? "neutral" : currentRatio >= 1.5 ? "good" : currentRatio >= 1 ? "warn" : "bad",
    },
    {
      title: "Накопленная прибыль",
      value: fmtMillions(String(retained), { sign: true, digits: 1 }),
      message: retained > 0 ? "Проект прибылен нарастающим итогом" : retained < 0 ? "Убыток за горизонт" : "В нуле",
      sub: retained < 0 ? "Проект не вышел на прибыльность" : "Нераспределённая прибыль на конец горизонта",
      status: retained > 0 ? "good" : retained < 0 ? "bad" : "neutral",
    },
    {
      title: "Чистые активы (оценка)",
      value: fmtMillions(result.valuation.net_assets, { digits: 1 }),
      message: retained >= 0 ? "Капитал растёт" : "Капитал сокращается",
      sub: result.valuation.gordon_value
        ? `По Гордону: ${fmtMillions(result.valuation.gordon_value, { digits: 1 })}`
        : "Активы минус обязательства",
      status: "neutral",
    },
  ];

  return (
    <div className="verdict-grid">
      {verdicts.map((v, i) => (
        <div key={v.title} className={`verdict-card verdict-card--${v.status}`}>
          {i === 0 && v.status === "good" && (
            <div className="verdict-card__cube">
              <CubeHero
                backdrop="transparent"
                showEnvironment={false}
                showOrbit={false}
                motionSpeed="calm"
                pointerTilt={false}
              />
            </div>
          )}
          <div className="verdict-card__stripe" />
          <div className="verdict-card__body">
            <div className="verdict-card__head">
              <span className="verdict-card__title">{v.title}</span>
              <span className={`verdict-badge verdict-badge--${v.status}`}>{BADGE[v.status]}</span>
            </div>
            <div
              className={
                "verdict-card__value" +
                (v.status === "good" ? " verdict-card__value--good" : v.status === "bad" ? " verdict-card__value--bad" : "")
              }
            >
              {v.value}
            </div>
            <div className="verdict-card__msg">{v.message}</div>
            {v.sub && <div className="verdict-card__sub">{v.sub}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}
