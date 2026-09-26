"""Закрывающие документы: счёт на оплату и акт оказанных услуг (пакет G, G6).

До них платформа брала деньги и не выдавала ни одного документа: бухгалтерия клиента не
могла провести расход, а оплату по счёту приходилось просить письмом. Правила слоя:

* **Реквизиты продавца — из окружения** (``SELLER_*``). Заданы не полностью или с
  ошибкой — документы **не формируются**, и отказ это называет. Бланк с пустыми или
  ошибочными реквизитами выглядел бы настоящим: оплату по нему отправили бы в никуда.
  Здесь строже, чем у реквизитов дела: там опечатка печатается как введена (решать
  человеку), а здесь по счёту уходят деньги.
* **Реквизиты покупателя — у организации**; ИНН проверяется тем же кодом, что у
  реквизитов дела (``audit_core.requisites.valid_inn``) — второй копии проверки нет.
* **Документ — снимок.** Реквизиты сторон, тариф, сумма и период записаны в нём на дату
  составления; перепечатка через год даёт тот же документ.
* **Акт — на каждый успешный платёж, датой окончания оплаченного периода**: услуга
  оказана к концу периода, не раньше. До этой даты акт назван будущим («будет сформирован
  …»), а у платежей, чей период не записан (до G6), — назван пробелом, а не угадан.
* **Счёт-фактура и УПД не формируются** — для них нужны электронный документооборот и
  учётная система продавца; это сказано рядом со списком документов (:data:`NOT_ISSUED`).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from itertools import cycle

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit_core.requisites import valid_inn

from .billing import checkout_amount
from .db_models import BillingDocument, Organization, Payment
from .plans import PRODUCT_NAME, Plan, get_plan

#: Реквизиты продавца: поле → (переменная окружения, как её назвать человеку).
SELLER_ENV: dict[str, tuple[str, str]] = {
    "name": ("SELLER_NAME", "полное наименование"),
    "inn": ("SELLER_INN", "ИНН"),
    "kpp": ("SELLER_KPP", "КПП"),
    "address": ("SELLER_ADDRESS", "адрес"),
    "bank": ("SELLER_BANK", "банк"),
    "bik": ("SELLER_BIK", "БИК"),
    "account": ("SELLER_ACCOUNT", "расчётный счёт"),
    "corr_account": ("SELLER_CORR_ACCOUNT", "корреспондентский счёт"),
    "director": ("SELLER_DIRECTOR", "руководитель, подписывающий документы"),
    "accountant": ("SELLER_ACCOUNTANT", "главный бухгалтер"),
    "vat_rate": ("SELLER_VAT_RATE", "ставка НДС"),
}

#: Без этих реквизитов документа нет. Главного бухгалтера может не быть (подписывает
#: руководитель), КПП нет у ИП, НДС нет у упрощёнки — эти пустоты правильны.
SELLER_REQUIRED = ("name", "inn", "address", "bank", "bik", "account", "corr_account",
                   "director")

#: Чего платформа не формирует — печатается рядом со списком документов.
NOT_ISSUED = ("Счёт-фактура и УПД не формируются: для них нужны электронный "
              "документооборот и учётная система продавца. Если они нужны вашей "
              "бухгалтерии, напишите платформе.")

#: Отказ клиенту, когда не готовы реквизиты **продавца**. Имена переменных окружения —
#: для экрана готовности установки (G9), а не для клиента: ему нужен выход, а не SELLER_BIK.
SELLER_NOT_READY = ("Платформа не указала свои реквизиты полностью — счета и акты пока не "
                    "формируются. Напишите платформе: счёт она выставит вручную.")

_KPP = re.compile(r"\d{4}[\dA-Z]{2}\d{3}")


def valid_kpp(value: str) -> bool:
    """КПП: 9 знаков — код налогового органа, причина постановки (цифры или буквы), номер."""
    return bool(_KPP.fullmatch(value.strip()))


def _key_ok(digits: str) -> bool:
    """Контрольный ключ счёта по правилам Банка России: веса 7-1-3 по 23 цифрам."""
    return sum(int(d) * w for d, w in zip(digits, cycle((7, 1, 3)), strict=False)) % 10 == 0


def valid_account(bik: str, account: str) -> bool:
    """Расчётный счёт сходится с БИК: ключ по трём последним цифрам БИК + 20 цифрам счёта.

    Это **не** подтверждение, что счёт существует, — только защита от опечатки, из-за
    которой оплата ушла бы в никуда.
    """
    return (len(bik) == 9 and bik.isdigit() and len(account) == 20 and account.isdigit()
            and _key_ok(bik[-3:] + account))


def valid_corr_account(bik: str, corr: str) -> bool:
    """Корреспондентский счёт сходится с БИК: ключ по «0» + 5–6-й цифрам БИК + счёту."""
    return (len(bik) == 9 and bik.isdigit() and len(corr) == 20 and corr.isdigit()
            and _key_ok("0" + bik[4:6] + corr))


def _vat(raw: str) -> int | None:
    """Ставка НДС из окружения. Пусто — продавец без НДС. Нечисло — ``ValueError``."""
    if not raw:
        return None
    value = int(raw)
    if not 0 <= value <= 30:
        raise ValueError(raw)
    return value


def seller_from_env() -> dict[str, str]:
    return {key: os.getenv(var, "").strip() for key, (var, _) in SELLER_ENV.items()}


def _inn_kpp_problems(inn: str, kpp: str, where: str) -> list[str]:
    problems = []
    if inn and not valid_inn(inn):
        problems.append(f"{where}ИНН «{inn}» не проходит проверку контрольной цифры")
    if len(inn) == 10 and not valid_kpp(kpp):
        problems.append(f"{where}у юридического лица (ИНН из 10 цифр) нужен КПП из 9 знаков")
    if len(inn) == 12 and kpp:
        problems.append(f"{where}у ИП (ИНН из 12 цифр) КПП не бывает — оставьте его пустым")
    return problems


def seller_problems(seller: dict[str, str] | None = None) -> list[str]:
    """Что не так с реквизитами продавца — словами и с именем переменной. Пусто — готово."""
    seller = seller if seller is not None else seller_from_env()
    problems = [f"не задано {SELLER_ENV[key][0]} — {SELLER_ENV[key][1]}"
                for key in SELLER_REQUIRED if not seller.get(key)]
    problems += _inn_kpp_problems(seller.get("inn", ""), seller.get("kpp", ""),
                                  "SELLER_INN/SELLER_KPP: ")
    bik, account, corr = seller.get("bik", ""), seller.get("account", ""), \
        seller.get("corr_account", "")
    if bik and (len(bik) != 9 or not bik.isdigit()):
        problems.append(f"SELLER_BIK: «{bik}» — БИК состоит из 9 цифр")
    elif bik:
        if account and not valid_account(bik, account):
            problems.append("SELLER_ACCOUNT: расчётный счёт не сходится с БИК по "
                            "контрольному ключу — похоже на опечатку")
        if corr and not valid_corr_account(bik, corr):
            problems.append("SELLER_CORR_ACCOUNT: корреспондентский счёт не сходится с "
                            "БИК по контрольному ключу — похоже на опечатку")
    try:
        _vat(seller.get("vat_rate", ""))
    except ValueError:
        problems.append(f"SELLER_VAT_RATE: «{seller.get('vat_rate')}» — ставка НДС "
                        "задаётся целым числом процентов; пусто — продавец без НДС")
    return problems


def seller_snapshot() -> dict:
    """Реквизиты продавца для документа (снимок). Зовётся только при пустом
    :func:`seller_problems`."""
    seller: dict = dict(seller_from_env())
    seller["vat_rate"] = _vat(seller["vat_rate"])
    return seller


# --- Покупатель ---

def buyer_problems(org: Organization) -> list[str]:
    """Что не так с реквизитами организации-покупателя. Пусто — документ формируется."""
    problems = [f"не заполнено: {label}" for value, label in (
        (org.legal_name, "полное наименование"), (org.inn, "ИНН"),
        (org.legal_address, "адрес")) if not value.strip()]
    return problems + _inn_kpp_problems(org.inn.strip(), org.kpp.strip(), "")


def buyer_snapshot(org: Organization) -> dict:
    return {"legal_name": org.legal_name.strip(), "inn": org.inn.strip(),
            "kpp": org.kpp.strip(), "address": org.legal_address.strip(),
            "name": org.name}


# --- Документы ---

class DocumentRefused(Exception):
    """Документ не формируется — с причиной словами для клиента."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _refuse_unless_ready(org: Organization) -> None:
    if seller_problems():
        raise DocumentRefused(SELLER_NOT_READY)
    problems = buyer_problems(org)
    if problems:
        raise DocumentRefused("Заполните реквизиты организации — без них документ не "
                              "формируется: " + "; ".join(problems) + ".")


#: Сколько раз пробовать взять номер, если его одновременно взял другой документ.
_NUMBER_TRIES = 3


def _insert_numbered(db: Session, doc: BillingDocument) -> BillingDocument:
    """Присвоить следующий номер ряда (вид + год) и сохранить.

    Номер — ``max + 1``; два документа, составленные одновременно, могли бы получить
    один номер, и это ловит уникальность в базе — тогда номер берётся заново.
    """
    for _ in range(_NUMBER_TRIES):
        doc.number = int(db.scalar(
            select(func.coalesce(func.max(BillingDocument.number), 0))
            .where(BillingDocument.kind == doc.kind, BillingDocument.year == doc.year))
            or 0) + 1
        db.add(doc)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(doc)
        return doc
    raise DocumentRefused("Не удалось присвоить документу номер — попробуйте ещё раз.")


#: Сколько месяцев можно указать в счёте. Счёт на оплату по безналу — обычно месяц,
#: квартал, полгода или год; больше года — договор, а не счёт.
INVOICE_MONTHS = range(1, 13)


def create_invoice(db: Session, org: Organization, plan: Plan, months: int, *,
                   requested_by: str, today: date) -> BillingDocument:
    """Счёт на оплату тарифа — по запросу клиента. Сумма — та же, что у оплаты в
    продукте (``billing.checkout_amount``): у безнала своей цены нет."""
    if plan.price_on_request or plan.price_rub <= 0:
        raise DocumentRefused(f"Тариф «{plan.name}» не оплачивается по счёту из продукта: "
                              "у него нет цены в прайсе. Условия и счёт — через платформу.")
    if months not in INVOICE_MONTHS:
        raise DocumentRefused("Счёт выставляется на срок от 1 до 12 месяцев.")
    _refuse_unless_ready(org)
    doc = BillingDocument(
        organization_id=org.id, kind="invoice", year=today.year, number=0, doc_date=today,
        plan_code=plan.code, plan_name=plan.name, product=plan.product, months=months,
        amount_rub=checkout_amount(plan, months), seller=seller_snapshot(),
        buyer=buyer_snapshot(org), created_by=requested_by)
    return _insert_numbered(db, doc)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def act_for(db: Session, payment_id: str) -> BillingDocument | None:
    return db.scalar(select(BillingDocument).where(BillingDocument.payment_id == payment_id))


def issue_act(db: Session, org: Organization, payment: Payment) -> BillingDocument:
    """Акт по успешному платежу — датой окончания оплаченного периода (снимок сторон на
    эту дату). Повторный вызов возвращает уже составленный: один платёж — один акт."""
    existing = act_for(db, payment.id)
    if existing is not None:
        return existing
    if payment.period_start is None or payment.period_end is None:
        raise DocumentRefused(NO_PERIOD)
    _refuse_unless_ready(org)
    plan = get_plan(payment.plan_code)
    end = _aware(payment.period_end)
    doc = BillingDocument(
        organization_id=org.id, kind="act", year=end.year, number=0, doc_date=end.date(),
        plan_code=plan.code, plan_name=plan.name, product=plan.product,
        months=payment.months, amount_rub=payment.amount_rub,
        period_start=payment.period_start, period_end=payment.period_end,
        payment_id=payment.id, seller=seller_snapshot(), buyer=buyer_snapshot(org))
    return _insert_numbered(db, doc)


NO_PERIOD = ("период этой оплаты не записан — платёж прошёл до появления актов; акт по "
             "нему выставит платформа по запросу")


def acts_due(db: Session, now: datetime) -> list[Payment]:
    """Успешные платежи, чей оплаченный период кончился, а акта ещё нет."""
    issued = select(BillingDocument.payment_id).where(BillingDocument.payment_id.is_not(None))
    rows = db.execute(select(Payment).where(
        Payment.status == "succeeded", Payment.period_end.is_not(None),
        Payment.id.not_in(issued))).scalars().all()
    return [p for p in rows if p.period_end is not None and _aware(p.period_end) <= now]


#: Состояние акта, которого ещё нет. Четыре, и ни одно не сводится к другому.
ACT_SCHEDULED = "scheduled"   # период ещё идёт — акт будет датой его окончания
ACT_DUE = "due"               # период кончился — акт составит ближайший ночной запуск
ACT_BLOCKED = "blocked"       # период кончился или кончится, но реквизиты не готовы
ACT_NO_PERIOD = "no_period"   # платёж до G6: период не записан, угадывать его нельзя


@dataclass
class UpcomingAct:
    """Акт, которого ещё нет: когда будет и что ему мешает."""

    payment_id: str
    paid_at: datetime
    plan_name: str
    amount_rub: int
    act_date: date | None
    state: str
    reason: str = ""


def upcoming_acts(db: Session, org: Organization, now: datetime) -> list[UpcomingAct]:
    """Оплаты организации без акта — и почему акта пока нет. Пустоты названы: будущая
    дата, неготовые реквизиты, период, которого платформа не знает."""
    issued = select(BillingDocument.payment_id).where(BillingDocument.payment_id.is_not(None))
    rows = db.execute(select(Payment).where(
        Payment.organization_id == org.id, Payment.status == "succeeded",
        Payment.id.not_in(issued)).order_by(Payment.created_at.desc())).scalars().all()
    blocked = (SELLER_NOT_READY if seller_problems()
               else "акт не формируется, пока не заполнены реквизиты организации"
               if buyer_problems(org) else "")
    out = []
    for p in rows:
        plan_name = get_plan(p.plan_code).name
        if p.period_end is None:
            out.append(UpcomingAct(p.id, p.created_at, plan_name, p.amount_rub, None,
                                   ACT_NO_PERIOD, NO_PERIOD))
            continue
        end = _aware(p.period_end)
        state = ACT_BLOCKED if blocked else ACT_DUE if end <= now else ACT_SCHEDULED
        out.append(UpcomingAct(p.id, p.created_at, plan_name, p.amount_rub, end.date(),
                               state, blocked))
    return out


def list_documents(db: Session, org_id: str) -> list[BillingDocument]:
    """Документы организации, новые сверху. Фильтр по ``organization_id`` — вся
    изоляция: RLS у таблицы нет (``db_models.NO_RLS_POLICY``)."""
    return list(db.execute(select(BillingDocument)
                           .where(BillingDocument.organization_id == org_id)
                           .order_by(BillingDocument.doc_date.desc(),
                                     BillingDocument.number.desc())).scalars())


def get_document(db: Session, org_id: str, doc_id: str) -> BillingDocument | None:
    doc = db.get(BillingDocument, doc_id)
    return doc if doc is not None and doc.organization_id == org_id else None


def title(doc: BillingDocument) -> str:
    """«Счёт № 12 от 26.09.2026» / «Акт № 7 от 20.10.2026»."""
    kind = "Счёт" if doc.kind == "invoice" else "Акт"
    return f"{kind} № {doc.number} от {doc.doc_date.strftime('%d.%m.%Y')}"


def service_line(doc: BillingDocument) -> str:
    """Наименование услуги в документе."""
    product = PRODUCT_NAME.get(doc.product, doc.product)
    if doc.kind == "act" and doc.period_start and doc.period_end:
        start = _aware(doc.period_start).strftime("%d.%m.%Y")
        end = _aware(doc.period_end).strftime("%d.%m.%Y")
        return (f"Предоставление доступа к сервису «{product}» по тарифу «{doc.plan_name}» "
                f"за период с {start} по {end}")
    return (f"Доступ к сервису «{product}», тариф «{doc.plan_name}», "
            f"{doc.months} мес.")
