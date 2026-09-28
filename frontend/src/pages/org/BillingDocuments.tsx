import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent } from "react";
import { httpDetail } from "../../api/client";
import {
  createInvoice, downloadBillingDocument, getBillingDocuments, getRequisites,
  saveRequisites, type BillingDocuments as Docs, type BuyerRequisitesIn, type Plan,
} from "../../api/org";
import { useToast } from "../../components/Toast";
import { Button, Field } from "../../components/ui";

const rub = (n: number) => `${n.toLocaleString("ru-RU")} ₽`;
const day = (iso: string) => new Date(iso).toLocaleDateString("ru-RU");

/** Сроки счёта: месяц, квартал, полгода, год — как платят по безналу. */
const INVOICE_MONTHS: [number, string][] = [[1, "1 месяц"], [3, "3 месяца"],
                                            [6, "6 месяцев"], [12, "12 месяцев"]];

/** Почему акта ещё нет — словами. Причину блокировки называет сервер. */
function upcomingText(u: Docs["upcoming"][number]): string {
  if (u.state === "scheduled" && u.act_date) return `будет сформирован ${day(u.act_date)}`;
  if (u.state === "due") return "будет сформирован при ближайшем ночном запуске";
  return u.reason;
}

/**
 * Счета, акты и реквизиты организации (G6).
 *
 * Документы собирает сервер из **снимка**: экран не рисует бланк сам, и скачанный через
 * год документ совпадает с составленным. Причины, по которым документа нет, приходят с
 * сервера словами и показываются как есть — будущая дата, неготовые реквизиты, платёж,
 * период которого платформа не знает. Чего платформа не формирует вовсе (счёт-фактура,
 * УПД), сказано рядом со списком: отсутствие не должно читаться как «забыли».
 */
export function BillingDocuments({ orgId, canManage, plans }: {
  orgId: string;
  canManage: boolean;
  plans: Plan[];
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const docs = useQuery({ queryKey: ["billing-docs", orgId],
                          queryFn: () => getBillingDocuments(orgId) });
  const req = useQuery({ queryKey: ["requisites", orgId], queryFn: () => getRequisites(orgId) });
  // Правка — поверх сохранённого; после сохранения форма снова берётся с сервера.
  const [draft, setDraft] = useState<BuyerRequisitesIn | null>(null);
  const payable = plans.filter((p) => p.price_rub > 0 && !p.price_on_request);
  const [planCode, setPlanCode] = useState("");
  const [months, setMonths] = useState(1);

  const form: BuyerRequisitesIn | null = draft ?? (req.data ? {
    legal_name: req.data.legal_name, inn: req.data.inn, kpp: req.data.kpp,
    legal_address: req.data.legal_address } : null);
  const edit = (key: keyof BuyerRequisitesIn) =>
    (e: ChangeEvent<HTMLInputElement>) => form && setDraft({ ...form, [key]: e.target.value });

  const save = useMutation({
    mutationFn: () => saveRequisites(orgId, form!),
    onSuccess: (saved) => {
      setDraft(null);
      qc.setQueryData(["requisites", orgId], saved);
      qc.invalidateQueries({ queryKey: ["billing-docs", orgId] });
      toast(saved.problems.length ? "Реквизиты сохранены, но в них есть что поправить"
                                  : "Реквизиты сохранены",
            { kind: saved.problems.length ? "error" : "success" });
    },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось сохранить реквизиты",
                                   { kind: "error" }),
  });

  const invoice = useMutation({
    mutationFn: () => createInvoice(orgId, planCode || payable[0]?.code, months),
    onSuccess: async (doc) => {
      qc.invalidateQueries({ queryKey: ["billing-docs", orgId] });
      toast(`${doc.title} выставлен`, { kind: "success" });
      await downloadBillingDocument(orgId, doc);
    },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось выставить счёт",
                                   { kind: "error" }),
  });

  const download = useMutation({
    mutationFn: (doc: Docs["documents"][number]) => downloadBillingDocument(orgId, doc),
    onError: () => toast("Не удалось скачать документ", { kind: "error" }),
  });

  const d = docs.data;
  return (
    <section className="billing-docs" aria-label="Документы">
      <div className="terms-head">Документы</div>
      {d && !d.seller_ready && (
        <div className="field-note field-note--warn" style={{ marginBottom: 12 }}>
          {d.seller_note}
        </div>
      )}

      <div className="billing-docs__grid">
        <div className="plan-current">
          <div className="plan-current__label">Реквизиты организации</div>
          {form && (
            <>
              <Field label="Полное наименование" value={form.legal_name}
                     placeholder="ООО «Ромашка»" disabled={!canManage}
                     onChange={edit("legal_name")} />
              <Field label="ИНН" value={form.inn} disabled={!canManage}
                     onChange={edit("inn")} />
              <Field label="КПП" value={form.kpp} disabled={!canManage}
                     note="У ИП КПП нет — оставьте пустым." onChange={edit("kpp")} />
              <Field label="Адрес" value={form.legal_address} disabled={!canManage}
                     onChange={edit("legal_address")} />
            </>
          )}
          {/* Опечатка в ИНН не отклоняется, а называется: исправлять её человеку, а
              документ с ней не сформируется. */}
          {req.data && req.data.problems.length > 0 && !draft && (
            <ul className="field-note field-note--warn billing-docs__problems">
              {req.data.problems.map((p) => <li key={p}>{p}</li>)}
            </ul>
          )}
          {canManage && (
            <Button loading={save.isPending} disabled={!draft}
                    onClick={() => save.mutate()}>
              Сохранить реквизиты
            </Button>
          )}
        </div>

        <div className="plan-current">
          <div className="plan-current__label">Счёт на оплату</div>
          {payable.length === 0 ? (
            <div className="field-note">
              У этого продукта нет тарифа с ценой в прайсе — счёт выставит платформа.
            </div>
          ) : (
            <>
              <label className="field">
                <span className="field__label">Тариф</span>
                <select className="input" aria-label="Тариф счёта" disabled={!canManage}
                        value={planCode || payable[0].code}
                        onChange={(e) => setPlanCode(e.target.value)}>
                  {payable.map((p) => (
                    <option key={p.code} value={p.code}>{p.name} · {rub(p.price_rub)}/мес</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Срок</span>
                <select className="input" aria-label="Срок счёта" disabled={!canManage}
                        value={months} onChange={(e) => setMonths(Number(e.target.value))}>
                  {INVOICE_MONTHS.map(([m, label]) => (
                    <option key={m} value={m}>{label}</option>
                  ))}
                </select>
              </label>
              <div className="field-note" style={{ marginBottom: 10 }}>
                Тариф включается после поступления оплаты: платформа назначит его по
                этому счёту, и оплаченный период начнётся с назначения.
              </div>
              {canManage && (
                <Button loading={invoice.isPending} onClick={() => invoice.mutate()}>
                  Выставить счёт
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      {d && (
        <div className="log-list billing-docs__list" role="table" aria-label="Счета и акты">
          <div className="log-row log-row--head" role="row">
            <div role="columnheader">Документ</div>
            <div role="columnheader">Тариф</div>
            <div role="columnheader">Сумма</div>
            <div role="columnheader" />
          </div>
          {d.documents.map((doc) => (
            <div className="log-row" role="row" key={doc.id}>
              <div role="rowheader">{doc.title}</div>
              <div role="cell">{doc.plan_name}, {doc.months} мес.</div>
              <div role="cell">{rub(doc.amount_rub)}</div>
              <div role="cell">
                <button type="button" className="link-btn"
                        onClick={() => download.mutate(doc)}>
                  Скачать DOCX
                </button>
              </div>
            </div>
          ))}
          {d.upcoming.map((u) => (
            <div className="log-row" role="row" key={u.payment_id}>
              <div role="rowheader">Акт за оплату от {day(u.paid_at)}</div>
              <div role="cell">{u.plan_name}</div>
              <div role="cell">{rub(u.amount_rub)}</div>
              <div role="cell" className="field-note">{upcomingText(u)}</div>
            </div>
          ))}
          {d.documents.length === 0 && d.upcoming.length === 0 && (
            <div className="log-row" role="row">
              <div role="cell">Документов пока нет.</div>
            </div>
          )}
        </div>
      )}
      {d && <div className="field-note" style={{ marginTop: 8 }}>{d.not_issued}</div>}
    </section>
  );
}
