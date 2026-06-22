import type {
  Deposit,
  EquityInjection,
  Financing,
  Lease,
  Loan,
  RepaymentType,
} from "../../api/model";
import { MonthlySeries } from "../../components/MonthlySeries";
import { Button, CheckField } from "../../components/ui";

interface Props {
  n: number;
  financing: Financing;
  onChange: (f: Financing) => void;
}

export function FinancingTab({ n, financing, onChange }: Props) {
  const { loans, equity, auto_financing } = financing;
  const leases = financing.leases ?? [];
  const deposits = financing.deposits ?? [];

  const addEquity = () => onChange({ ...financing, equity: [...equity, { amount: "0", month: 0 }] });
  const updEquity = (i: number, patch: Partial<EquityInjection>) =>
    onChange({ ...financing, equity: equity.map((e, k) => (k === i ? { ...e, ...patch } : e)) });
  const rmEquity = (i: number) => onChange({ ...financing, equity: equity.filter((_, k) => k !== i) });

  const addLoan = () =>
    onChange({ ...financing, loans: [...loans, { name: "Кредит", amount: "0", start_month: 0, term_months: 12, annual_rate: "0.18", repayment: "equal_principal" }] });
  const updLoan = (i: number, patch: Partial<Loan>) =>
    onChange({ ...financing, loans: loans.map((l, k) => (k === i ? { ...l, ...patch } : l)) });
  const rmLoan = (i: number) => onChange({ ...financing, loans: loans.filter((_, k) => k !== i) });

  const addLease = () =>
    onChange({ ...financing, leases: [...leases, { name: "Лизинг", monthly_payment: "0", start_month: 0, term_months: 12 }] });
  const updLease = (i: number, patch: Partial<Lease>) =>
    onChange({ ...financing, leases: leases.map((l, k) => (k === i ? { ...l, ...patch } : l)) });
  const rmLease = (i: number) => onChange({ ...financing, leases: leases.filter((_, k) => k !== i) });

  const addDeposit = () =>
    onChange({ ...financing, deposits: [...deposits, { name: "Депозит", amount: "0", start_month: 0, term_months: 12, annual_rate: "0.08" }] });
  const updDeposit = (i: number, patch: Partial<Deposit>) =>
    onChange({ ...financing, deposits: deposits.map((d, k) => (k === i ? { ...d, ...patch } : d)) });
  const rmDeposit = (i: number) => onChange({ ...financing, deposits: deposits.filter((_, k) => k !== i) });

  return (
    <div>
      <div className="section-head">
        <h2>Акционерный капитал</h2>
        <Button onClick={addEquity}>+ Взнос</Button>
      </div>
      {equity.map((e, i) => (
        <div className="row-card" key={i}>
          <div className="row-head">
            <label className="field grow"><span>Сумма</span>
              <input className="input" type="number" value={e.amount} onChange={(ev) => updEquity(i, { amount: ev.target.value })} /></label>
            <label className="field"><span>Месяц</span>
              <input className="input" type="number" value={e.month} onChange={(ev) => updEquity(i, { month: parseInt(ev.target.value || "0", 10) })} /></label>
            <Button variant="ghost" onClick={() => rmEquity(i)}>Удалить</Button>
          </div>
        </div>
      ))}

      <div className="section-head" style={{ marginTop: 20 }}>
        <h2>Займы</h2>
        <Button onClick={addLoan}>+ Заём</Button>
      </div>
      {loans.map((l, i) => (
        <div className="row-card" key={i}>
          <div className="row-head">
            <input className="input grow" value={l.name} onChange={(e) => updLoan(i, { name: e.target.value })} />
            <Button variant="ghost" onClick={() => rmLoan(i)}>Удалить</Button>
          </div>
          <div className="form-grid">
            <label className="field"><span>{l.foreign ? "Сумма (валюта)" : "Сумма"}</span>
              <input className="input" type="number" value={l.amount} onChange={(e) => updLoan(i, { amount: e.target.value })} /></label>
            <label className="field"><span>Месяц получения</span>
              <input className="input" type="number" value={l.start_month} onChange={(e) => updLoan(i, { start_month: parseInt(e.target.value || "0", 10) })} /></label>
            <label className="field"><span>Срок, мес.</span>
              <input className="input" type="number" value={l.term_months} onChange={(e) => updLoan(i, { term_months: parseInt(e.target.value || "1", 10) })} /></label>
            <label className="field"><span>Ставка (год)</span>
              <input className="input" type="number" step="0.01" value={l.annual_rate} onChange={(e) => updLoan(i, { annual_rate: e.target.value })} /></label>
            <label className="field"><span>Погашение</span>
              <select className="select" value={l.repayment} onChange={(e) => updLoan(i, { repayment: e.target.value as RepaymentType })}>
                <option value="equal_principal">Равными долями</option>
                <option value="bullet">В конце срока</option>
              </select></label>
          </div>
          <div className="toolbar" style={{ marginTop: 8, gap: 20 }}>
            <CheckField label="Валютный (по курсу FX)" checked={l.foreign ?? false}
                        onChange={(foreign) => updLoan(i, { foreign })} />
            <CheckField label="Проценты на прибыль (невычитаемые)" checked={l.interest_on_profit ?? false}
                        onChange={(interest_on_profit) => updLoan(i, { interest_on_profit })} />
          </div>
        </div>
      ))}

      <div className="section-head" style={{ marginTop: 20 }}>
        <h2>Лизинг</h2>
        <Button onClick={addLease}>+ Лизинг</Button>
      </div>
      {leases.map((l, i) => (
        <div className="row-card" key={i}>
          <div className="row-head">
            <input className="input grow" value={l.name} onChange={(e) => updLease(i, { name: e.target.value })} />
            <Button variant="ghost" onClick={() => rmLease(i)}>Удалить</Button>
          </div>
          <div className="form-grid">
            <label className="field"><span>Платёж в месяц</span>
              <input className="input" type="number" value={l.monthly_payment} onChange={(e) => updLease(i, { monthly_payment: e.target.value })} /></label>
            <label className="field"><span>Месяц начала</span>
              <input className="input" type="number" value={l.start_month} onChange={(e) => updLease(i, { start_month: parseInt(e.target.value || "0", 10) })} /></label>
            <label className="field"><span>Срок, мес.</span>
              <input className="input" type="number" value={l.term_months} onChange={(e) => updLease(i, { term_months: parseInt(e.target.value || "1", 10) })} /></label>
          </div>
        </div>
      ))}

      <div className="section-head" style={{ marginTop: 20 }}>
        <h2>Депозиты / ЦБ</h2>
        <Button onClick={addDeposit}>+ Депозит</Button>
      </div>
      {deposits.map((d, i) => (
        <div className="row-card" key={i}>
          <div className="row-head">
            <input className="input grow" value={d.name} onChange={(e) => updDeposit(i, { name: e.target.value })} />
            <Button variant="ghost" onClick={() => rmDeposit(i)}>Удалить</Button>
          </div>
          <div className="form-grid">
            <label className="field"><span>Сумма размещения</span>
              <input className="input" type="number" value={d.amount} onChange={(e) => updDeposit(i, { amount: e.target.value })} /></label>
            <label className="field"><span>Месяц размещения</span>
              <input className="input" type="number" value={d.start_month} onChange={(e) => updDeposit(i, { start_month: parseInt(e.target.value || "0", 10) })} /></label>
            <label className="field"><span>Срок, мес.</span>
              <input className="input" type="number" value={d.term_months} onChange={(e) => updDeposit(i, { term_months: parseInt(e.target.value || "1", 10) })} /></label>
            <label className="field"><span>Ставка дохода (год)</span>
              <input className="input" type="number" step="0.01" value={d.annual_rate} onChange={(e) => updDeposit(i, { annual_rate: e.target.value })} /></label>
          </div>
        </div>
      ))}

      <h2 style={{ marginTop: 20 }}>Акции и дивиденды</h2>
      <div className="row-card">
        <div className="form-grid">
          <label className="field"><span>Обыкновенных акций, шт.</span>
            <input className="input" type="number" value={financing.common_shares}
                   onChange={(e) => onChange({ ...financing, common_shares: e.target.value })} /></label>
        </div>
        <MonthlySeries n={n} label="Дивиденды по месяцам" values={financing.dividends}
                       onChange={(dividends) => onChange({ ...financing, dividends })} />
      </div>

      <h2 style={{ marginTop: 20 }}>Автоподбор финансирования</h2>
      <div className="row-card">
        <label className="checkbox">
          <input type="checkbox" checked={auto_financing.enabled}
                 onChange={(e) => onChange({ ...financing, auto_financing: { ...auto_financing, enabled: e.target.checked } })} />
          Покрывать дефицит наличности кредитной линией
        </label>
        <div className="form-grid" style={{ marginTop: 12 }}>
          <label className="field"><span>Ставка (год)</span>
            <input className="input" type="number" step="0.01" value={auto_financing.annual_rate}
                   onChange={(e) => onChange({ ...financing, auto_financing: { ...auto_financing, annual_rate: e.target.value } })} /></label>
          <label className="field"><span>Мин. остаток</span>
            <input className="input" type="number" value={auto_financing.min_balance}
                   onChange={(e) => onChange({ ...financing, auto_financing: { ...auto_financing, min_balance: e.target.value } })} /></label>
        </div>
      </div>
    </div>
  );
}
