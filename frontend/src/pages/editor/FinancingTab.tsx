import { useEffect, useRef, useState } from "react";
import type {
  Deposit,
  EquityInjection,
  Financing,
  Lease,
  Loan,
  RepaymentType,
} from "../../api/model";
import { EField, EPercentField, ESelect } from "../../components/EditorField";
import { IconTrash, IconX } from "../../components/icons";
import { MonthlyGrid } from "../../components/MonthlyGrid";
import { Button, CountChip, Switch } from "../../components/ui";

interface Props {
  n: number;
  financing: Financing;
  onChange: (f: Financing) => void;
}

const SECTIONS = [
  ["equity", "Капитал"],
  ["loans", "Займы"],
  ["leases", "Лизинг"],
  ["deposits", "Депозиты"],
  ["shares", "Акции и дивиденды"],
  ["auto", "Автоподбор"],
] as const;

type SectionKey = (typeof SECTIONS)[number][0];

/** Вкладка «Финансирование» (макет «Этап 9»): 6 секций + sticky-TOC со скролл-спаем. */
export function FinancingTab({ n, financing, onChange }: Props) {
  const { loans, equity, auto_financing } = financing;
  const leases = financing.leases ?? [];
  const deposits = financing.deposits ?? [];

  const [active, setActive] = useState<SectionKey>("equity");
  const refs = useRef<Partial<Record<SectionKey, HTMLDivElement | null>>>({});

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length === 0) return;
        const top = visible.reduce((a, b) =>
          a.boundingClientRect.top < b.boundingClientRect.top ? a : b,
        );
        setActive(top.target.getAttribute("data-sec") as SectionKey);
      },
      { rootMargin: "-15% 0px -65% 0px" },
    );
    Object.values(refs.current).forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, []);

  const scrollTo = (key: SectionKey) => {
    refs.current[key]?.scrollIntoView({ behavior: "smooth", block: "start" });
    setActive(key);
  };

  const counts: Record<SectionKey, number> = {
    equity: equity.length,
    loans: loans.length,
    leases: leases.length,
    deposits: deposits.length,
    shares: 0,
    auto: auto_financing.enabled ? 1 : 0,
  };

  const addEquity = () => onChange({ ...financing, equity: [...equity, { amount: "0", month: 0 }] });
  const updEquity = (i: number, patch: Partial<EquityInjection>) =>
    onChange({ ...financing, equity: equity.map((e, k) => (k === i ? { ...e, ...patch } : e)) });
  const rmEquity = (i: number) => onChange({ ...financing, equity: equity.filter((_, k) => k !== i) });

  const addLoan = () =>
    onChange({
      ...financing,
      loans: [
        ...loans,
        { name: "Кредит", amount: "0", start_month: 0, term_months: 12, annual_rate: "0.18", repayment: "equal_principal" },
      ],
    });
  const updLoan = (i: number, patch: Partial<Loan>) =>
    onChange({ ...financing, loans: loans.map((l, k) => (k === i ? { ...l, ...patch } : l)) });
  const rmLoan = (i: number) => onChange({ ...financing, loans: loans.filter((_, k) => k !== i) });

  const addLease = () =>
    onChange({
      ...financing,
      leases: [...leases, { name: "Лизинг", monthly_payment: "0", start_month: 0, term_months: 12 }],
    });
  const updLease = (i: number, patch: Partial<Lease>) =>
    onChange({ ...financing, leases: leases.map((l, k) => (k === i ? { ...l, ...patch } : l)) });
  const rmLease = (i: number) => onChange({ ...financing, leases: leases.filter((_, k) => k !== i) });

  const addDeposit = () =>
    onChange({
      ...financing,
      deposits: [...deposits, { name: "Депозит", amount: "0", start_month: 0, term_months: 12, annual_rate: "0.08" }],
    });
  const updDeposit = (i: number, patch: Partial<Deposit>) =>
    onChange({ ...financing, deposits: deposits.map((d, k) => (k === i ? { ...d, ...patch } : d)) });
  const rmDeposit = (i: number) => onChange({ ...financing, deposits: deposits.filter((_, k) => k !== i) });

  const section = (key: SectionKey, title: string, desc: string, action: React.ReactNode, body: React.ReactNode) => (
    <div
      className="csec"
      data-sec={key}
      ref={(el) => {
        refs.current[key] = el;
      }}
      style={{ scrollMarginTop: 14, marginBottom: 0 }}
    >
      <div className="csec__head">
        <div style={{ minWidth: 0 }}>
          <div className="csec__titlerow">
            <span className="csec__dot" />
            <span className="csec__title">{title}</span>
            {counts[key] > 0 && key !== "auto" && <CountChip>{counts[key]}</CountChip>}
          </div>
          <div className="csec__desc">{desc}</div>
        </div>
        {action}
      </div>
      {body}
    </div>
  );

  return (
    <div>
      <div className="tab-head">
        <div style={{ minWidth: 0 }}>
          <div className="tab-head__title">Финансирование — источники средств</div>
          <div className="tab-head__sub">Капитал, займы, лизинг, депозиты, дивиденды и автоподбор.</div>
        </div>
      </div>

      <div className="fin-chips">
        {SECTIONS.map(([key, label]) => (
          <button key={key} type="button" onClick={() => scrollTo(key)}>
            {label}
            {counts[key] > 0 && key !== "auto" ? ` · ${counts[key]}` : ""}
          </button>
        ))}
      </div>

      <div className="fin-layout">
        <nav className="fin-toc">
          <div className="fin-toc__head">Разделы</div>
          {SECTIONS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={"fin-toc__item" + (active === key ? " fin-toc__item--active" : "")}
              onClick={() => scrollTo(key)}
            >
              <span className="fin-toc__dot" />
              {label}
              {counts[key] > 0 && key !== "auto" && <span className="fin-toc__count">{counts[key]}</span>}
            </button>
          ))}
        </nav>

        <div className="fin-body">
          {section(
            "equity",
            "Акционерный капитал",
            "Взносы собственников — источник собственного финансирования.",
            <Button onClick={addEquity}>＋&nbsp;&nbsp;Взнос</Button>,
            equity.length === 0 ? (
              <p className="muted" style={{ fontSize: 13 }}>
                Пока нет взносов. Добавьте сумму и месяц поступления.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {equity.map((e, i) => (
                  <div className="mini-row" key={i}>
                    <div className="mini-row__idx">{i + 1}</div>
                    <div style={{ flex: 2, minWidth: 0 }}>
                      <EField label="Сумма" prefix="₽" value={e.amount} onChange={(v) => updEquity(i, { amount: v })} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <EField
                        label="Месяц"
                        prefix="М"
                        value={e.month}
                        onChange={(v) => updEquity(i, { month: parseInt(v || "0", 10) || 0 })}
                      />
                    </div>
                    <button type="button" className="mini-row__x" title="Удалить взнос" onClick={() => rmEquity(i)}>
                      <IconX size={14} />
                    </button>
                  </div>
                ))}
              </div>
            ),
          )}

          {section(
            "loans",
            "Займы",
            "Заёмное финансирование с процентами; график — равными долями или в конце срока.",
            <Button onClick={addLoan}>＋&nbsp;&nbsp;Заём</Button>,
            loans.length === 0 ? (
              <p className="muted" style={{ fontSize: 13 }}>
                Пока нет займов.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {loans.map((l, i) => (
                  <div className="line-card" key={i}>
                    <div className="line-card__head">
                      <div className="line-card__idx">{i + 1}</div>
                      <div className="line-card__name">
                        <input value={l.name} placeholder="Название займа" onChange={(e) => updLoan(i, { name: e.target.value })} />
                      </div>
                      {l.foreign && <span className="prop-chip prop-chip--cur">Валютный</span>}
                      {l.interest_on_profit && <span className="prop-chip prop-chip--profit">% из прибыли</span>}
                      <button type="button" className="line-card__del" title="Удалить" onClick={() => rmLoan(i)}>
                        <IconTrash size={16} />
                      </button>
                    </div>
                    <div className="esec__grid">
                      <EField
                        label={l.foreign ? "Сумма (валюта)" : "Сумма"}
                        prefix={l.foreign ? "$" : "₽"}
                        value={l.amount}
                        onChange={(v) => updLoan(i, { amount: v })}
                      />
                      <EField
                        label="Месяц получения"
                        prefix="М"
                        value={l.start_month}
                        onChange={(v) => updLoan(i, { start_month: parseInt(v || "0", 10) || 0 })}
                      />
                      <EField
                        label="Срок"
                        suffix="мес."
                        value={l.term_months}
                        onChange={(v) => updLoan(i, { term_months: parseInt(v || "0", 10) || 0 })}
                      />
                      <EPercentField
                        label="Ставка"
                        suffix="% / год"
                        value={l.annual_rate}
                        onChange={(v) => updLoan(i, { annual_rate: v })}
                      />
                      <ESelect
                        label="Погашение"
                        value={l.repayment}
                        onChange={(v) => updLoan(i, { repayment: v as RepaymentType })}
                        options={[
                          ["equal_principal", "Равными долями"],
                          ["bullet", "В конце срока"],
                        ]}
                      />
                    </div>
                    <div style={{ marginTop: 14, display: "flex", gap: 22, flexWrap: "wrap" }}>
                      <Switch
                        label="Валютный (по курсу FX)"
                        checked={l.foreign ?? false}
                        onChange={(foreign) => updLoan(i, { foreign })}
                      />
                      <Switch
                        label="Проценты из прибыли (невычитаемые)"
                        checked={l.interest_on_profit ?? false}
                        onChange={(interest_on_profit) => updLoan(i, { interest_on_profit })}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ),
          )}

          {section(
            "leases",
            "Лизинг",
            "Операционный — издержка периода; финансовый — капитализация предмета лизинга.",
            <Button onClick={addLease}>＋&nbsp;&nbsp;Лизинг</Button>,
            leases.length === 0 ? (
              <p className="muted" style={{ fontSize: 13 }}>
                Пока нет договоров лизинга.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {leases.map((l, i) => (
                  <div className="line-card" key={i}>
                    <div className="line-card__head">
                      <div className="line-card__idx">{i + 1}</div>
                      <div className="line-card__name">
                        <input value={l.name} placeholder="Предмет лизинга" onChange={(e) => updLease(i, { name: e.target.value })} />
                      </div>
                      <span className="prop-chip">{l.finance ? "финансовый" : "операционный"}</span>
                      <button type="button" className="line-card__del" title="Удалить" onClick={() => rmLease(i)}>
                        <IconTrash size={16} />
                      </button>
                    </div>
                    <div className="esec__grid">
                      <EField
                        label="Платёж"
                        prefix="₽"
                        suffix="/ мес"
                        value={l.monthly_payment}
                        onChange={(v) => updLease(i, { monthly_payment: v })}
                      />
                      <EField
                        label="Месяц начала"
                        prefix="М"
                        value={l.start_month}
                        onChange={(v) => updLease(i, { start_month: parseInt(v || "0", 10) || 0 })}
                      />
                      <EField
                        label="Срок"
                        suffix="мес."
                        value={l.term_months}
                        onChange={(v) => updLease(i, { term_months: parseInt(v || "0", 10) || 0 })}
                      />
                      {l.finance && (
                        <EPercentField
                          label="Ставка лизинга"
                          suffix="% / год"
                          hint="Ставка для приведённой стоимости предмета финансового лизинга"
                          value={l.annual_rate ?? "0"}
                          onChange={(v) => updLease(i, { annual_rate: v })}
                        />
                      )}
                    </div>
                    <div style={{ marginTop: 14 }}>
                      <Switch
                        label="Финансовый лизинг (капитализация предмета → B19)"
                        checked={l.finance ?? false}
                        onChange={(finance) => updLease(i, { finance })}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ),
          )}

          {section(
            "deposits",
            "Депозиты / ЦБ",
            "Размещение свободных средств под процент.",
            <Button onClick={addDeposit}>＋&nbsp;&nbsp;Депозит</Button>,
            deposits.length === 0 ? (
              <p className="muted" style={{ fontSize: 13 }}>
                Пока нет размещений.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {deposits.map((d, i) => (
                  <div className="line-card" key={i}>
                    <div className="line-card__head">
                      <div className="line-card__idx">{i + 1}</div>
                      <div className="line-card__name">
                        <input value={d.name} placeholder="Название" onChange={(e) => updDeposit(i, { name: e.target.value })} />
                      </div>
                      <button type="button" className="line-card__del" title="Удалить" onClick={() => rmDeposit(i)}>
                        <IconTrash size={16} />
                      </button>
                    </div>
                    <div className="esec__grid">
                      <EField
                        label="Сумма размещения"
                        prefix="₽"
                        value={d.amount}
                        onChange={(v) => updDeposit(i, { amount: v })}
                      />
                      <EField
                        label="Месяц размещения"
                        prefix="М"
                        value={d.start_month}
                        onChange={(v) => updDeposit(i, { start_month: parseInt(v || "0", 10) || 0 })}
                      />
                      <EField
                        label="Срок"
                        suffix="мес."
                        value={d.term_months}
                        onChange={(v) => updDeposit(i, { term_months: parseInt(v || "0", 10) || 0 })}
                      />
                      <EPercentField
                        label="Ставка дохода"
                        suffix="% / год"
                        value={d.annual_rate}
                        onChange={(v) => updDeposit(i, { annual_rate: v })}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ),
          )}

          {section(
            "shares",
            "Акции и дивиденды",
            "Число обыкновенных акций и выплаты дивидендов по месяцам.",
            null,
            <div className="line-card">
              <div className="esec__grid" style={{ marginBottom: 14 }}>
                <EField
                  label="Обыкновенных акций"
                  suffix="шт."
                  value={financing.common_shares}
                  onChange={(v) => onChange({ ...financing, common_shares: v })}
                />
              </div>
              <MonthlyGrid
                n={n}
                rows={[
                  {
                    key: "dividends",
                    title: "Дивиденды, ₽",
                    values: financing.dividends,
                    onChange: (dividends) => onChange({ ...financing, dividends }),
                    unit: "₽",
                  },
                ]}
              />
            </div>,
          )}

          {section(
            "auto",
            "Автоподбор финансирования",
            "Кредитная линия закрывает кассовые разрывы автоматически.",
            null,
            <div className="line-card">
              <Switch
                label="Покрывать дефицит наличности кредитной линией"
                checked={auto_financing.enabled}
                onChange={(enabled) =>
                  onChange({ ...financing, auto_financing: { ...auto_financing, enabled } })
                }
              />
              {auto_financing.enabled && (
                <div className="esec__grid" style={{ marginTop: 14 }}>
                  <EPercentField
                    label="Ставка"
                    suffix="% / год"
                    value={auto_financing.annual_rate}
                    onChange={(v) =>
                      onChange({ ...financing, auto_financing: { ...auto_financing, annual_rate: v } })
                    }
                  />
                  <EField
                    label="Мин. остаток"
                    prefix="₽"
                    hint="Ниже этого остатка денежных средств линия добирает финансирование"
                    value={auto_financing.min_balance}
                    onChange={(v) =>
                      onChange({ ...financing, auto_financing: { ...auto_financing, min_balance: v } })
                    }
                  />
                </div>
              )}
            </div>,
          )}
        </div>
      </div>
    </div>
  );
}
