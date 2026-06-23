import type { ProjectModel } from "./api/model";

export type Severity = "error" | "warn";
export interface Issue {
  severity: Severity;
  message: string;
}

const num = (s: string | number | undefined | null): number => {
  const x = Number(s ?? 0);
  return Number.isFinite(x) ? x : 0;
};

const fmt = (x: number) => x.toLocaleString("ru-RU", { maximumFractionDigits: 0 });

/** Клиентская проверка модели: ловит частые ошибки ввода до отправки на расчёт. */
export function validateModel(m: ProjectModel): Issue[] {
  const issues: Issue[] = [];
  const s = m.settings;

  // Стартовый баланс должен сходиться, иначе расчёт вернёт ошибку (актив = пассив).
  const sb = m.company.starting_balance;
  const assets = num(sb.cash) + num(sb.fixed_assets_net) + num(sb.receivables)
    + num(sb.foreign_monetary) * num(m.environment.fx_open);
  const liab = num(sb.debt) + num(sb.payables) + num(sb.paid_in_capital) + num(sb.retained_earnings);
  if (Math.abs(assets - liab) > 0.01) {
    issues.push({
      severity: "error",
      message: `Стартовый баланс не сходится: актив ${fmt(assets)} ≠ пассив ${fmt(liab)} (разница ${fmt(assets - liab)}). Расчёт вернёт ошибку.`,
    });
  }

  // Оценка по Гордону: темп роста g должен быть меньше ставки дисконтирования.
  const g = num(s.terminal_growth_rate);
  if (g > 0 && g >= num(s.discount_rate_annual)) {
    issues.push({
      severity: "warn",
      message: "Темп роста g ≥ ставки дисконтирования — оценка по Гордону не будет рассчитана.",
    });
  }

  // Ставки/доли, которые задаются долей и должны быть в диапазоне 0–1.
  const shareWarn = (v: number, label: string) => {
    if (v < 0 || v > 1) {
      issues.push({ severity: "warn", message: `${label}: значение ${v} вне диапазона 0–1 (задаётся долей).` });
    }
  };
  shareWarn(num(s.profit_tax_rate), "Налог на прибыль");
  shareWarn(num(s.vat_rate), "НДС");
  shareWarn(num(s.profit_tax_benefit_share), "Льгота по прибыли");
  shareWarn(num(s.sales_tax_rate), "Налог с продаж");

  // Предоплата по каждой строке сбыта — доля 0–1.
  m.operating_plan.sales.forEach((line, i) => {
    const p = num(line.payment.prepayment_share);
    if (p < 0 || p > 1) {
      issues.push({ severity: "error", message: `Сбыт, строка ${i + 1}: предоплата ${p} вне диапазона 0–1.` });
    }
  });

  // Длительность горизонта.
  if (num(m.header.duration_months) < 1) {
    issues.push({ severity: "error", message: "Длительность проекта должна быть не меньше 1 месяца." });
  }

  return issues;
}
