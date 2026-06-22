import { line, type CalcResponse } from "../api/calc";
import { money, percent, ratio } from "../format";

type Status = "ok" | "warn" | "bad" | "flat";

interface Verdict {
  title: string;
  value: string;
  note: string;
  status: Status;
}

const COLOR: Record<Status, string> = {
  ok: "#16a34a",
  warn: "#d97706",
  bad: "#dc2626",
  flat: "#94a3b8",
};

const last = (a: number[]) => (a.length ? a[a.length - 1] : 0);

/** Сводка-вердикт по проекту: ключевые выводы одним экраном. */
export function SummaryView({ result }: { result: CalcResponse }) {
  const m = result.metrics;
  const cash = line(result.balance, "B1").map(Number);
  const minCash = cash.length ? Math.min(...cash) : 0;
  const retained = last(line(result.balance, "B32").map(Number));
  const b8 = last(line(result.balance, "B8").map(Number));
  const b25 = last(line(result.balance, "B25").map(Number));
  const currentRatio = b25 > 0 ? b8 / b25 : null;
  const npv = Number(m.npv);

  const verdicts: Verdict[] = [
    {
      title: "Чистая приведённая стоимость (NPV)",
      value: money(m.npv),
      note: npv > 0 ? "Проект создаёт стоимость" : npv < 0 ? "Проект разрушает стоимость" : "На грани окупаемости",
      status: npv > 0 ? "ok" : npv < 0 ? "bad" : "warn",
    },
    {
      title: "Внутренняя норма доходности (IRR)",
      value: percent(m.irr_annual),
      note: m.irr_annual == null ? "Не определена (нет смены знака потока)" : "Годовая доходность проекта",
      status: m.irr_annual == null ? "flat" : "ok",
    },
    {
      title: "Индекс прибыльности (PI)",
      value: m.pi ? ratio(m.pi) : "—",
      note: m.pi == null ? "—" : Number(m.pi) >= 1 ? "Отдача выше вложений" : "Отдача ниже вложений",
      status: m.pi == null ? "flat" : Number(m.pi) >= 1 ? "ok" : "bad",
    },
    {
      title: "Срок окупаемости",
      value: m.pb_months != null ? `${m.pb_months} мес.` : "—",
      note: m.pb_months != null ? `Дисконт.: ${m.dpb_months != null ? m.dpb_months + " мес." : "за горизонтом"}` : "Не окупается за горизонт",
      status: m.pb_months != null ? "ok" : "warn",
    },
    {
      title: "Минимальный остаток денег",
      value: money(String(minCash)),
      note: minCash < 0 ? "Кассовый разрыв — требуется финансирование" : "Кассовых разрывов нет",
      status: minCash < 0 ? "bad" : "ok",
    },
    {
      title: "Потребность в финансировании",
      value: m.peak_financing_need ? money(m.peak_financing_need) : "—",
      note: "Приведённый дефицит до выхода в плюс",
      status: "flat",
    },
    {
      title: "Текущая ликвидность",
      value: currentRatio != null ? currentRatio.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) : "—",
      note: currentRatio == null ? "Нет краткосрочных обязательств" : currentRatio >= 1 ? "Активы покрывают обязательства" : "Обязательства выше текущих активов",
      status: currentRatio == null ? "flat" : currentRatio >= 1 ? "ok" : "warn",
    },
    {
      title: "Накопленная прибыль",
      value: money(String(retained)),
      note: retained > 0 ? "Проект прибылен нарастающим итогом" : "Накопленный убыток на конец горизонта",
      status: retained > 0 ? "ok" : retained < 0 ? "bad" : "flat",
    },
    {
      title: "Чистые активы (оценка)",
      value: money(result.valuation.net_assets),
      note: result.valuation.gordon_value ? `По Гордону: ${money(result.valuation.gordon_value)}` : "Собственный капитал на конец",
      status: "flat",
    },
  ];

  return (
    <div>
      <div className="summary-grid">
        {verdicts.map((v) => (
          <div className="summary-card" key={v.title} style={{ borderLeft: `4px solid ${COLOR[v.status]}` }}>
            <div className="m-label">{v.title}</div>
            <div className="m-value">{v.value}</div>
            <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{v.note}</div>
          </div>
        ))}
      </div>
      {result.warnings.length > 0 && (
        <div className="warnings" style={{ marginTop: 14 }}>
          <strong>Предупреждения расчёта:</strong> {result.warnings.join("; ")}
        </div>
      )}
    </div>
  );
}
