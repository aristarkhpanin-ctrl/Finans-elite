// Применение отчётности из ГИР БО к делу (пакет L, L3).
//
// Сервер разбирает ответ ресурса ФНС и сопоставляет строки (audit_core/girbo.py); здесь —
// только наложение на модель дела, как у импорта Excel: модель меняется на экране, а
// сохраняет её человек — со всеми проверками дела.
//
// Периоды заменяются годами из ресурса, и всё, что в деле привязано к периодам, но в
// ресурсе отсутствует (амортизация, капитализация, переоценки, нормализация, план
// продавца), **переносится по совпадающей подписи периода**. Без пары — сбрасывается, и
// это называется: молча обнулённая переоценка выглядела бы как её отсутствие.
import type { AuditModel, GirboPreview } from "./api/audit";

export interface GirboApplyResult {
  model: AuditModel;
  /** Что перенесено на совпадающие годы. */
  carried: string[];
  /** Что потеряло введённые значения: годов-пар для них в загрузке нет. */
  dropped: string[];
  /** Какие реквизиты фирмы-цели заполнены из реестра (только пустые). */
  filled: string[];
}

const MEMO_NAMES: Record<string, string> = {
  M_DEPRECIATION: "амортизация",
  M_MARKET_CAP: "рыночная капитализация",
  M_RETAINED: "нераспределённая прибыль",
};

const nonZero = (v: string | undefined) => {
  const x = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(x) && x !== 0;
};

/** Ряд старых периодов → ряд новых по подписи; `lost` — пропало ли что-то ненулевое. */
function remap(series: string[] | undefined, from: string[], to: string[]) {
  const values = to.map((label) => {
    const i = from.indexOf(label);
    return i >= 0 ? (series?.[i] ?? "0") : "0";
  });
  const lost = from.some((label, i) => !to.includes(label) && nonZero(series?.[i]));
  const kept = values.some(nonZero);
  return { values, lost, kept };
}

export function applyGirbo(model: AuditModel, preview: GirboPreview,
                           opts: { fillRequisites: boolean }): GirboApplyResult {
  const from = model.periods.map((p) => p.label);
  const to = preview.periods;
  const carried: string[] = [];
  const dropped: string[] = [];
  const track = (name: string, r: { lost: boolean; kept: boolean }) => {
    if (r.kept) carried.push(name);
    if (r.lost) dropped.push(name);
  };

  const table = (old: Record<string, string[]>, fresh: Record<string, string[]>) => {
    const out: Record<string, string[]> = { ...fresh };
    for (const [code, series] of Object.entries(old)) {
      if (code in fresh) continue;
      const r = remap(series, from, to);
      track(MEMO_NAMES[code] ?? code, r);
      out[code] = r.values;
    }
    return out;
  };
  const balance = table(model.balance ?? {}, preview.balance);
  const income = table(model.income ?? {}, preview.income);

  const revaluations = (model.revaluations ?? []).map((x) => {
    const r = remap(x.amounts, from, to);
    track(`переоценка «${x.label || x.code}»`, r);
    return { ...x, amounts: r.values };
  });
  const earnings = (model.earnings_adjustments ?? []).map((x) => {
    const r = remap(x.amounts, from, to);
    track(`нормализация «${x.label}»`, r);
    return { ...x, amounts: r.values };
  });
  const plan: Record<string, string[]> = {};
  for (const [code, series] of Object.entries(model.seller_plan ?? {})) {
    const r = remap(series, from, to);
    track(`план продавца (${code})`, r);
    plan[code] = r.values;
  }

  const report = { ...(model.report ?? {}) };
  const filled: string[] = [];
  if (opts.fillRequisites) {
    const reg = preview.registry;
    const fill = (key: "subject_full_name" | "subject_inn" | "subject_ogrn" | "subject_address",
                  value: string, label: string) => {
      if (!String(report[key] ?? "").trim() && value) {
        report[key] = value;
        filled.push(label);
      }
    };
    fill("subject_full_name", reg.full_name ?? "", "наименование");
    fill("subject_inn", reg.inn ?? "", "ИНН");
    fill("subject_ogrn", reg.ogrn ?? "", "ОГРН");
    fill("subject_address", reg.address ?? "", "адрес");
  }

  return {
    model: {
      ...model,
      periods: to.map((label) => ({ label, kind: "year" as const })),
      balance,
      income,
      revaluations,
      earnings_adjustments: earnings,
      seller_plan: plan,
      report,
      registry: preview.registry,
    },
    carried,
    dropped,
    filled,
  };
}

/** Сводка года для предпросмотра: выручка, чистая прибыль и итог баланса — в рублях. */
export function yearSummary(preview: GirboPreview, t: number) {
  const n = (table: Record<string, string[]>, code: string) => Number(table[code]?.[t] ?? 0);
  const inc = preview.income;
  const net = n(inc, "I_REVENUE") - n(inc, "I_COGS") - n(inc, "I_OPEX") - n(inc, "I_INTEREST")
    + n(inc, "I_OTHER") - n(inc, "I_TAX");
  const bal = preview.balance;
  const assets = ["A_FIXED", "A_INVENTORY", "A_RECEIVABLE", "A_CASH"]
    .reduce((s, code) => s + n(bal, code), 0);
  return { revenue: n(inc, "I_REVENUE"), net, assets };
}
