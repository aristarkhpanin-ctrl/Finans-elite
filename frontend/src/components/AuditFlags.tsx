import { useState } from "react";
import type { AuditFlag, AuditFlagRegistry } from "../api/audit";
import { fmtMoney } from "../format";

/**
 * Реестр красных флагов (макет «Экран 9»; методика — SPEC, Приложение И).
 *
 * Главное здесь — итог. Макет складывает влияние всех флагов в «цену рисков», но
 * денежная мера есть **не у всякого** флага: отрицательный капитал или непокрытые
 * проценты не выражаются суммой, которую покупатель вычтет из цены. Поэтому итог
 * называет две величины — сумму оценённых и **число неоценённых**, — и никогда не
 * выдаёт первую за полную цену рисков.
 */

const SEVERITY: Record<AuditFlag["severity"], { label: string; cls: string }> = {
  risk: { label: "Риск", cls: "flag--risk" },
  warning: { label: "Внимание", cls: "flag--warn" },
};

export function AuditFlags({
  registry,
  periods,
}: {
  registry: AuditFlagRegistry;
  periods: string[];
}) {
  const [open, setOpen] = useState<string | null>(null);
  const flags = registry.flags ?? [];

  if (flags.length === 0) {
    return (
      <div className="tab-empty">
        <div className="tab-empty__title">Красных флагов нет</div>
        <div className="tab-empty__sub">
          По введённой отчётности признаков приукрашивания не найдено. Реестр опирается
          только на агрегатные формы: процедуры, которым нужны выписки, договоры и
          реестр залогов, здесь не выполняются — таких данных в деле нет.
        </div>
      </div>
    );
  }

  const risks = flags.filter((f) => f.severity === "risk").length;
  const priced = flags.filter((f) => f.impact !== null).length;

  return (
    <div>
      <div className="flag-total">
        <div>
          <div className="mini-label">Оценённое влияние</div>
          {/* Ноль рублей при отсутствии оценённых флагов читался бы как «риски ничего
              не стоят» — а на деле их просто нечем измерить. */}
          <div className="flag-total__val">
            {priced === 0 ? "не определено" : fmtMoney(registry.priced_total)}
          </div>
        </div>
        <div className="flag-total__note">
          {/* Число неоценённых — не сноска, а часть итога: без него сумма читается
              как полная цена рисков, хотя часть рисков в неё не вошла вовсе. */}
          {priced === 0 ? (
            <>
              Ни один из найденных флагов не выражается суммой: их влияние на цену —
              предмет переговоров, а не расчёта.
            </>
          ) : registry.unpriced > 0 ? (
            <>
              Сумма — только по флагам с денежной мерой. Ещё <b>{registry.unpriced}</b>{" "}
              {registry.unpriced === 1 ? "флаг не выражается" : "флагов не выражаются"}{" "}
              суммой: их влияние на цену — предмет переговоров, а не расчёта.
            </>
          ) : (
            <>Все флаги имеют денежную меру и вошли в сумму.</>
          )}
        </div>
      </div>

      <div className="page-sub" style={{ margin: "14px 0 10px" }}>
        {flags.length} {flags.length === 1 ? "флаг" : "флагов"}
        {risks > 0 && <> · из них {risks} тяжёлых</>}
      </div>

      <div className="flag-list">
        {flags.map((f) => {
          const expanded = open === f.code;
          return (
            <div className={"flag " + SEVERITY[f.severity].cls} key={f.code}>
              <button
                type="button"
                className="flag__head"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : f.code)}
              >
                <span className="flag__badge">{SEVERITY[f.severity].label}</span>
                <span className="flag__title">{f.title}</span>
                {f.periods.length > 0 && (
                  <span className="flag__periods">
                    {f.periods.map((t) => periods[t] ?? `Период ${t + 1}`).join(", ")}
                  </span>
                )}
                <span className="flag__impact">
                  {/* Прочерк, а не ноль: «нет меры» и «влияние ноль» — разные вещи. */}
                  {f.impact === null ? "мера не определена" : fmtMoney(f.impact)}
                </span>
              </button>

              <div className="flag__detail">{f.detail}</div>

              {expanded && Object.keys(f.evidence).length > 0 && (
                <table className="flag__evidence">
                  <tbody>
                    {Object.entries(f.evidence).map(([key, value]) => (
                      <tr key={key}>
                        <td>{EVIDENCE[key] ?? key}</td>
                        <td className="flag__num">{fmtMoney(value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Подписи слагаемых находки: код без расшифровки читателю ничего не говорит. */
const EVIDENCE: Record<string, string> = {
  receivables_growth: "Рост дебиторки",
  revenue_growth: "Рост выручки",
  expected_receivables: "Дебиторка при прежней оборачиваемости",
  inventory_growth: "Рост запасов",
  cogs_growth: "Рост себестоимости",
  expected_inventory: "Запасы при прежней оборачиваемости",
  net_profit: "Чистая прибыль",
  cash_drop: "Падение денежных средств",
  other_income: "Прочие доходы",
  min_equity: "Минимальный капитал",
  worst_gap: "Худший разрыв EBIT и процентов",
  gap: "Превышение",
  margin_was: "Маржа была",
  margin_now: "Маржа стала",
};
