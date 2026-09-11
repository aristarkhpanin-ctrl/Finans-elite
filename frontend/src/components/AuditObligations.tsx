import {
  COVENANT_STATUSES,
  OBLIGATION_KINDS,
  type AuditObligations as Register,
  type CovenantStatus,
  type Obligation,
  type ObligationKind,
  emptyObligation,
  isOffBalanceKind,
} from "../api/audit";
import { useEffect, useState } from "react";
import { IconTrash } from "./icons";
import { Button } from "./ui";
import { fmtMoney, fracToPct, pctToFrac, plural } from "../format";

/**
 * Обязательства и залоги (макет «Экран 10»; методика — SPEC, Приложение Л).
 *
 * Три решения методики видны прямо на экране.
 *
 * **Забалансовое не складывается с балансовым.** Итога два, они стоят рядом, и общей
 * суммы у них нет. Сложить значило бы утверждать, что поручительство уже наступило;
 * спрятать — что его нет.
 *
 * **Расхождение с балансом показывается всегда.** Реестр, который молча согласился с
 * балансом, выглядел бы полным, будучи половиной.
 *
 * **График — это долг по годам погашения, а не платежи года.** Амортизацию долга в
 * модель не вводят, и «равные доли по годам» были бы выдуманными условиями договора.
 */

const STATUS_CLS: Record<CovenantStatus, string> = {
  ok: "cov--ok",
  breached: "cov--bad",
  unknown: "cov--unknown",
};

const pct = (v: string | null): string =>
  v === null ? "—" : `${(Number(v) * 100).toLocaleString("ru-RU",
    { maximumFractionDigits: 0 })}%`;

/** Ставка на просмотр. Сдвиг запятой строкой: `0.164 × 100` во float даёт 16.400000000000002. */
const rate = (v: string | null): string =>
  v === null ? "—" : `${fracToPct(v).replace(".", ",")}%`;

/**
 * Ставка на ввод: модель хранит долю, поле показывает проценты.
 *
 * Черновик набирается локально. Без него поле, выведенное из модели пересчётом,
 * стирало бы набираемую запятую («15,» → «15»), и десятичную ставку было бы не
 * ввести вовсе. Пустое поле даёт `null` — «не указана», а не ноль: беспроцентный
 * займ и займ без указанной ставки — разные факты.
 */
function RateInput({ value, onChange, label }: {
  value: string | null;
  onChange: (next: string | null) => void;
  label: string;
}) {
  const [draft, setDraft] = useState(() => fracToPct(value ?? ""));

  useEffect(() => {
    const canonical = value ?? "";
    if (pctToFrac(draft) !== canonical && !(draft === "" && canonical === "")) {
      setDraft(fracToPct(value ?? ""));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <input
      className="input" inputMode="decimal" placeholder="не указана"
      aria-label={label} value={draft}
      onChange={(e) => {
        setDraft(e.target.value);
        if (e.target.value.trim() === "") return onChange(null);
        const frac = pctToFrac(e.target.value);
        // Промежуточный ввод («15,») в модель не уходит и черновик не сбрасывает.
        if (frac !== "") onChange(frac);
      }}
    />
  );
}

export function AuditObligations({
  register,
  obligations,
  onChange,
}: {
  register: Register;
  obligations: Obligation[];
  onChange: (next: Obligation[]) => void;
}) {
  const upd = (i: number, patch: Partial<Obligation>) =>
    onChange(obligations.map((o, k) => (k === i ? { ...o, ...patch } : o)));

  const rows = register.rows ?? [];
  const balanceRows = rows.filter((r) => !r.off_balance);
  const offRows = rows.filter((r) => r.off_balance);
  const peak = register.buckets.reduce(
    (m, b) => Math.max(m, Math.abs(Number(b.amount))), 0);

  return (
    <div>
      {/* ── Два итога, между ними явно сказано, почему они не складываются ── */}
      <div className="obl-totals">
        <div className="obl-total">
          <div className="mini-label">Долг в балансе</div>
          <div className="obl-total__val">{fmtMoney(register.balance_debt)}</div>
          <div className="obl-total__sub">
            {balanceRows.length === 0
              ? "реестр не заполнен"
              : `${balanceRows.length} ${plural(balanceRows.length, "договор",
                                                "договора", "договоров")}`}
          </div>
        </div>
        <div className="obl-total obl-total--off">
          <div className="mini-label">Забалансовые обязательства</div>
          <div className="obl-total__val">{fmtMoney(register.off_balance)}</div>
          <div className="obl-total__sub">
            {offRows.length === 0
              ? "поручительств и залогов за третьих лиц не введено"
              : `${offRows.length} ${plural(offRows.length, "обязательство",
                                            "обязательства", "обязательств")}`}
          </div>
        </div>
        {/* Не сноска, а часть итога: без неё читатель сложит две цифры сам. */}
        <div className="obl-totals__note">
          Эти две величины <b>не складываются</b>. Забалансовое обязательство ещё не
          наступило: оно станет долгом в тот день, когда основной должник перестанет
          платить, — и до этого дня его нет ни в активе, ни в пассиве.
        </div>
      </div>

      {/* ── Сверка с балансом: показывается всегда, включая «сошлось» ── */}
      <div className={"obl-recon " + (register.rows.length === 0 ? "obl-recon--idle"
                                      : register.reconciled ? "obl-recon--ok"
                                      : "obl-recon--bad")}>
        <div>
          <div className="mini-label">Долг по отчётности</div>
          <div className="obl-recon__val">{fmtMoney(register.reported_debt)}</div>
        </div>
        <div className="obl-recon__text">
          {register.rows.length === 0 ? (
            <>
              Реестр пуст, сверять нечего. Обязательства не выводятся из отчётности:
              из двух строк-агрегатов не видно ни кому должны, ни под какой залог, ни
              что случится при нарушении ковенанта.
            </>
          ) : register.reconciled ? (
            <>Реестр сходится с балансом: весь долг отчётности назван по договорам.</>
          ) : Number(register.discrepancy) > 0 ? (
            <>
              В реестре не хватает <b>{fmtMoney(register.discrepancy)}</b> против
              баланса. Часть долга не названа: неизвестно, кому она, под какой залог и
              с какими ковенантами.
            </>
          ) : (
            <>
              Реестр шире баланса на{" "}
              <b>{fmtMoney(String(-Number(register.discrepancy)))}</b>. Либо в него попало
              условное обязательство, либо отчётность неполна.
            </>
          )}
        </div>
      </div>

      {/* ── Долг по годам погашения ── */}
      {register.buckets.length > 0 && (
        <div className="audit-block">
          <div className="audit-block__title">Долг по годам погашения</div>
          <div className="page-sub" style={{ marginBottom: 12 }}>
            Это <b>не</b> график платежей: амортизация долга в реестр не вводится, и
            раскладывать остаток «равными долями» значило бы выдумать условия
            договоров. Остаток отнесён целиком к году погашения — так виден год, в
            который упирается рефинансирование.
          </div>
          <div className="obl-bars">
            {register.buckets.map((b) => (
              <div className="obl-bar" key={b.label}>
                <div className="obl-bar__label">{b.label}</div>
                <div className="obl-bar__track">
                  <div
                    className={"obl-bar__fill" + (b.kind === "year" ? "" : " obl-bar__fill--odd")}
                    style={{ width: peak > 0
                      ? `${Math.max(2, (Math.abs(Number(b.amount)) / peak) * 100)}%` : "2%" }}
                  />
                </div>
                <div className="obl-bar__val">{fmtMoney(b.amount)}</div>
              </div>
            ))}
          </div>
          {register.buckets.some((b) => b.kind === "unknown") && (
            <div className="field-note field-note--warn">
              У части договоров срок погашения не заполнен — эта сумма стоит отдельной
              строкой, а не разнесена по годам наугад.
            </div>
          )}
        </div>
      )}

      {/* ── Залоги ── */}
      <div className="audit-block">
        <div className="audit-block__title">Залоги</div>
        {register.pledged_share === null ? (
          <div className="field-note">
            Долю заложенного считать не от чего: активов в отчётности нет.
          </div>
        ) : (
          <div className="obl-pledge">
            <div>
              <div className="mini-label">Под залогом</div>
              <div className="obl-total__val">
                {fmtMoney(register.pledged_total)}{" "}
                <span className="obl-pledge__pct">{pct(register.pledged_share)} активов</span>
              </div>
            </div>
            <div>
              <div className="mini-label">Свободно от обременения</div>
              <div className="obl-total__val">{fmtMoney(register.free_assets ?? "0")}</div>
            </div>
            <div className="obl-totals__note">
              Свободные активы — предел, в котором покупатель сможет привлечь новое
              финансирование без согласия текущих кредиторов.
            </div>
          </div>
        )}
      </div>

      {/* ── Ковенанты ── */}
      {(register.covenants_breached > 0 || register.covenants_unknown > 0) && (
        <div className="audit-block">
          <div className="audit-block__title">Ковенанты</div>
          <div className="page-sub">
            {register.covenants_breached > 0 && (
              <>
                Нарушено: <b>{register.covenants_breached}</b>. Нарушенный ковенант даёт
                кредитору право досрочного истребования — такой долг перестаёт быть
                долгосрочным.{" "}
              </>
            )}
            {register.covenants_unknown > 0 && (
              <>
                Не проверено: <b>{register.covenants_unknown}</b>. Непроверенный ковенант
                не считается соблюдённым: условия договора не сводятся к нашим
                показателям автоматически — в договоре свои определения долга и EBITDA.
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Ввод реестра ── */}
      <div className="audit-block">
        <div className="tab-head" style={{ marginBottom: 10 }}>
          <div className="audit-block__title" style={{ marginBottom: 0 }}>
            Реестр обязательств
          </div>
          <Button variant="ghost"
                  onClick={() => onChange([...obligations, emptyObligation()])}>
            ＋&nbsp;&nbsp;Обязательство
          </Button>
        </div>

        {obligations.length === 0 ? (
          <div className="field-note">
            Обязательств не введено. Пустой реестр — это «не заполнено», а не
            «обязательств нет»: пока он пуст, ни сверка с балансом, ни флаги по
            ковенантам и залогам не считаются.
          </div>
        ) : (
          obligations.map((o, i) => (
            <div className="obl-editor" key={i}>
              <div className="obl-editor__row">
                <input className="input" placeholder="Кредитор"
                       aria-label={`Обязательство ${i + 1}: кредитор`}
                       value={o.creditor}
                       onChange={(e) => upd(i, { creditor: e.target.value })} />
                <input className="input" placeholder="Договор: номер и дата"
                       aria-label={`Обязательство ${i + 1}: договор`}
                       value={o.contract}
                       onChange={(e) => upd(i, { contract: e.target.value })} />
                <select className="select" aria-label={`Обязательство ${i + 1}: вид`}
                        value={o.kind}
                        onChange={(e) => upd(i, { kind: e.target.value as ObligationKind })}>
                  {OBLIGATION_KINDS.map(([k, label]) => (
                    <option key={k} value={k}>{label}</option>
                  ))}
                </select>
                <button type="button" className="icon-action icon-action--danger"
                        title={`Удалить обязательство «${o.creditor || "без кредитора"}»`}
                        onClick={() => onChange(obligations.filter((_, k) => k !== i))}>
                  <IconTrash size={15} />
                </button>
              </div>

              <div className="obl-editor__row">
                <label className="obl-cell">
                  <span className="mini-label">
                    {isOffBalanceKind(o.kind) ? "Сумма обязательства" : "Остаток долга"}
                  </span>
                  <input className="input" inputMode="decimal" value={o.amount}
                         aria-label={`Обязательство ${i + 1}: сумма`}
                         onChange={(e) => upd(i, { amount: e.target.value })} />
                </label>
                <label className="obl-cell">
                  <span className="mini-label">Ставка, % годовых</span>
                  <RateInput value={o.rate} label={`Обязательство ${i + 1}: ставка`}
                             onChange={(next) => upd(i, { rate: next })} />
                </label>
                <label className="obl-cell">
                  <span className="mini-label">Год погашения</span>
                  <input className="input" inputMode="numeric" placeholder="не указан"
                         aria-label={`Обязательство ${i + 1}: год погашения`}
                         disabled={o.on_demand}
                         value={o.maturity_year === null ? "" : String(o.maturity_year)}
                         onChange={(e) => upd(i, {
                           maturity_year: e.target.value.trim() === "" ? null
                                          : Number(e.target.value),
                         })} />
                </label>
                <label className="obl-cell obl-cell--check">
                  <input type="checkbox" checked={o.on_demand}
                         onChange={(e) => upd(i, { on_demand: e.target.checked,
                                                   maturity_year: e.target.checked ? null
                                                                  : o.maturity_year })} />
                  <span>По требованию</span>
                </label>
              </div>

              <div className="obl-editor__row">
                <input className="input obl-editor__wide"
                       placeholder="Обеспечение (что заложено)"
                       aria-label={`Обязательство ${i + 1}: обеспечение`}
                       value={o.collateral}
                       onChange={(e) => upd(i, { collateral: e.target.value })} />
                <label className="obl-cell">
                  <span className="mini-label">Оценка залога</span>
                  <input className="input" inputMode="decimal" placeholder="0"
                         aria-label={`Обязательство ${i + 1}: оценка залога`}
                         value={o.pledged_amount}
                         onChange={(e) => upd(i, { pledged_amount: e.target.value })} />
                </label>
              </div>

              <div className="obl-editor__row">
                <input className="input" placeholder="Ковенант («Долг/EBITDA ≤ 2.5×»)"
                       aria-label={`Обязательство ${i + 1}: ковенант`}
                       value={o.covenant}
                       onChange={(e) => upd(i, { covenant: e.target.value })} />
                <select className={"select " + STATUS_CLS[o.covenant_status]}
                        aria-label={`Обязательство ${i + 1}: статус ковенанта`}
                        value={o.covenant_status}
                        onChange={(e) => upd(i, {
                          covenant_status: e.target.value as CovenantStatus })}>
                  {COVENANT_STATUSES.map(([s, label]) => (
                    <option key={s} value={s}>{label}</option>
                  ))}
                </select>
                <input className="input" placeholder="Последствие нарушения по договору"
                       aria-label={`Обязательство ${i + 1}: последствие нарушения`}
                       value={o.covenant_note}
                       onChange={(e) => upd(i, { covenant_note: e.target.value })} />
              </div>

              {o.covenant.trim() !== "" && o.covenant_status === "unknown" && (
                <div className="field-note field-note--warn obl-editor__note">
                  Статус ковенанта ставите вы: свести условие договора к нашим
                  показателям нельзя — в договоре свои определения долга и EBITDA.
                  Пока стоит «не проверен», соблюдённым он не считается.
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* ── Свод строк реестра ── */}
      {rows.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className="audit-grid obl-table">
            <thead>
              <tr>
                <th className="audit-grid__rowhead">Кредитор и договор</th>
                <th>Вид</th>
                <th>Сумма</th>
                <th>Ставка</th>
                <th>Погашение</th>
                <th>Обеспечение</th>
                <th>Ковенант</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={r.off_balance ? "obl-row--off" : undefined}>
                  <td className="audit-grid__rowhead">
                    {r.creditor || "—"}
                    <span className="eq-kind">{r.contract || "договор не указан"}</span>
                  </td>
                  <td>{r.kind_label}</td>
                  <td>{fmtMoney(r.amount)}</td>
                  <td>{rate(r.rate)}</td>
                  <td className={r.maturity === "срок не указан" ? "obl-cell--warn"
                                 : undefined}>{r.maturity}</td>
                  <td>{r.collateral || "без обеспечения"}</td>
                  <td>
                    {r.covenant ? (
                      <span className={"obl-cov " + STATUS_CLS[r.covenant_status]}>
                        {COVENANT_STATUSES.find(([s]) => s === r.covenant_status)?.[1]}
                        <span className="eq-kind">{r.covenant}</span>
                      </span>
                    ) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
