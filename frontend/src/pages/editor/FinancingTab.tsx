import type { EquityInjection, Financing, Loan, RepaymentType } from "../../api/model";
import { Button } from "../../components/ui";

interface Props {
  financing: Financing;
  onChange: (f: Financing) => void;
}

export function FinancingTab({ financing, onChange }: Props) {
  const { loans, equity, auto_financing } = financing;

  const addEquity = () => onChange({ ...financing, equity: [...equity, { amount: "0", month: 0 }] });
  const updEquity = (i: number, patch: Partial<EquityInjection>) =>
    onChange({ ...financing, equity: equity.map((e, k) => (k === i ? { ...e, ...patch } : e)) });
  const rmEquity = (i: number) => onChange({ ...financing, equity: equity.filter((_, k) => k !== i) });

  const addLoan = () =>
    onChange({ ...financing, loans: [...loans, { name: "Кредит", amount: "0", start_month: 0, term_months: 12, annual_rate: "0.18", repayment: "equal_principal" }] });
  const updLoan = (i: number, patch: Partial<Loan>) =>
    onChange({ ...financing, loans: loans.map((l, k) => (k === i ? { ...l, ...patch } : l)) });
  const rmLoan = (i: number) => onChange({ ...financing, loans: loans.filter((_, k) => k !== i) });

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
            <label className="field"><span>Сумма</span>
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
        </div>
      ))}

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
