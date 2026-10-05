"""Тарифы, подписка и платежи (биллинг, 6.5)."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import billing, closing_docs, crud, usage
from ..billing import PaymentProvider, get_payment_provider
from ..billing_period import RENEW_AHEAD
from ..closing_docx import build_document_docx
from ..database import get_db
from ..db_models import User
from ..deps import current_user, require_membership, require_org_permission
from ..docgen import DOCX_MIME
from ..plans import (
    DEFAULT_PLANS,
    PLANS,
    PRODUCTS,
    UNIT_NAME,
    get_plan,
    is_valid_plan,
    product_of,
)
from ..rbac import Perm
from ..schemas import (
    BillingDocumentOut,
    BillingDocumentsOut,
    BuyerRequisitesIn,
    BuyerRequisitesOut,
    CheckoutQuoteOut,
    CheckoutRequest,
    CheckoutResponse,
    InvoiceRequest,
    PlanOut,
    SubscriptionOut,
    SubscriptionUpdate,
    UpcomingActOut,
)

router = APIRouter(prefix="/api/v1", tags=["billing"])


def _plan_out(p) -> PlanOut:
    # Годом оплачивается только то, что оплачивается помесячно: у бесплатного и
    # «по запросу» годовой цены нет, и ноль вместо неё читался бы как «даром».
    annual = (billing.checkout_amount(p, 12)
              if p.price_rub > 0 and not p.price_on_request else None)
    gift = (billing.free_months(12)
            if annual is not None and annual < p.price_rub * 12 else 0)
    return PlanOut(code=p.code, product=p.product, name=p.name, price_rub=p.price_rub,
                   price_on_request=p.price_on_request, max_units=p.max_units,
                   unit_name=UNIT_NAME.get(p.product, "объектов"),
                   max_members=p.max_members, annual_price_rub=annual,
                   annual_free_months=gift)


@router.get("/plans", response_model=list[PlanOut])
def list_plans(product: str | None = None) -> list[PlanOut]:
    """Каталог тарифов (публично); ``product`` — только тарифы одного продукта."""
    return [_plan_out(p) for p in PLANS.values() if product is None or p.product == product]


def _subscription_out(db: Session, org_id: str, product: str,
                      provider: PaymentProvider) -> SubscriptionOut:
    sub = crud.get_subscription(db, org_id, product)
    plan = billing.current_plan(db, org_id, product)
    used = (crud.count_audit_subjects(db, org_id) if product == "audit"
            else crud.count_projects(db, org_id))
    auto = bool(sub and sub.auto_renew)
    end = sub.current_period_end if sub else None
    unavailable = billing.auto_renew_unavailable(provider)
    return SubscriptionOut(
        product=product,
        plan_code=plan.code,
        plan_name=plan.name,
        status=sub.status if sub else "active",
        current_period_end=sub.current_period_end if sub else None,
        price_rub=plan.price_rub,
        price_on_request=plan.price_on_request,
        max_units=plan.max_units,
        unit_name=UNIT_NAME.get(product, "объектов"),
        max_members=plan.max_members,
        used_units=used,
        used_members=crud.count_members(db, org_id),
        auto_renew=auto,
        payment_method_title=sub.payment_method_title if sub and auto else "",
        renew_months=sub.renew_months if sub and auto else 1,
        renew_amount_rub=sub.renew_amount_rub if sub and auto else None,
        next_charge_at=end - RENEW_AHEAD if auto and end is not None else None,
        renew_error=sub.renew_error if sub else "",
        renew_attempts=sub.renew_attempts if sub and auto else 0,
        auto_renew_available=unavailable is None,
        auto_renew_unavailable_reason=unavailable or "",
    )


@router.get("/organizations/{org_id}/subscription", response_model=SubscriptionOut)
def get_subscription(product: str = "business",
                     org_id: str = Depends(require_membership),
                     provider: PaymentProvider = Depends(get_payment_provider),
                     db: Session = Depends(get_db)) -> SubscriptionOut:
    """Подписка организации на продукт (с использованием квот)."""
    return _subscription_out(db, org_id, product, provider)


@router.get("/organizations/{org_id}/subscriptions", response_model=list[SubscriptionOut])
def get_subscriptions(org_id: str = Depends(require_membership),
                      provider: PaymentProvider = Depends(get_payment_provider),
                      db: Session = Depends(get_db)) -> list[SubscriptionOut]:
    """Подписки организации по всем продуктам — их столько же, сколько продуктов."""
    return [_subscription_out(db, org_id, p, provider) for p in PRODUCTS]


@router.post("/organizations/{org_id}/subscription", response_model=SubscriptionOut)
def change_subscription(body: SubscriptionUpdate,
                        org_id: str = Depends(require_org_permission(Perm.BILLING_MANAGE)),
                        user: User = Depends(current_user),
                        provider: PaymentProvider = Depends(get_payment_provider),
                        db: Session = Depends(get_db)) -> SubscriptionOut:
    """Перейти на тариф, за который не платят, — то есть **вниз**, на бесплатный (F1).

    Раньше этот маршрут менял тариф на любой: право `billing.manage` есть у владельца
    организации-клиента, и «Корпоративный» брался одним запросом бесплатно. Хуже:
    ``set_plan`` звался без ``paid``, поэтому срок не ставился вовсе — самовыданный
    тариф не истекал никогда, и режим чтения при неоплате (B2) на него не срабатывал.

    **Платный тариф выдаёт платёж, а не право.** Отказ называет обе дороги: оплатить
    или получить назначение от платформы (оплата по счёту). Уйти на бесплатный клиент
    по-прежнему может сам — это отказ от услуги, а не её получение.
    """
    if not is_valid_plan(body.plan_code):
        raise HTTPException(status_code=422, detail=f"Неизвестный тариф: {body.plan_code}")
    plan = get_plan(body.plan_code)
    if not billing.is_self_service(plan):
        raise HTTPException(
            status_code=403,
            detail=(f"Тариф «{plan.name}» включается оплатой. Оплатите его в разделе "
                    "«Тариф и оплата» либо запросите назначение у платформы, если "
                    "оплачиваете по счёту."))
    # Продукт выводится из кода тарифа, а не приходит отдельным полем: два источника
    # правды разошлись бы, и организация получила бы тариф «Аудита» в подписке «Элит».
    product = product_of(body.plan_code)
    # Прежний тариф читается **до** смены: после неё его уже никто не вспомнит, а без
    # него запись не отвечает «с чего ушли» — и отток по ней не посчитать (F8).
    #
    # Запоминается **строка, а не строка подписки**: `set_plan` правит тот же самый
    # объект, и ссылка на него после смены назвала бы новый тариф прежним («free → free»
    # вместо «team → free») — то есть записала бы, что ухода не было.
    subscription = crud.get_subscription(db, org_id, product)
    was = subscription.plan_code if subscription else DEFAULT_PLANS.get(product, "")
    # ``paid=True`` с бесплатным тарифом **стирает** чужой срок: уходя с платного,
    # организация не должна тащить за собой его дату (см. `crud.set_plan`).
    crud.set_plan(db, org_id, body.plan_code, product=product, period_end=None, paid=True)
    crud.log_action(db, org_id, user, "billing.plan_change", entity_type="organization",
                    entity_id=org_id, entity_name=body.plan_code,
                    details=billing.plan_change_details(product, was, body.plan_code))
    return _subscription_out(db, org_id, product, provider)


@router.post("/organizations/{org_id}/billing/checkout", response_model=CheckoutResponse)
def checkout(body: CheckoutRequest,
             org_id: str = Depends(require_org_permission(Perm.BILLING_MANAGE)),
             user: User = Depends(current_user),
             provider: PaymentProvider = Depends(get_payment_provider),
             db: Session = Depends(get_db)) -> CheckoutResponse:
    """Инициировать смену тарифа через провайдера (ЮKassa — ссылка оплаты; ручной — сразу).

    **Тариф «по запросу» через оплату не проходит** (F1). Его цена — ноль, и ручной
    провайдер включал его немедленно и бесплатно, а ЮKassa получила бы платёж на 0 ₽.
    Условия такого тарифа согласуют вне продукта, и назначает его платформа.
    """
    if not is_valid_plan(body.plan_code):
        raise HTTPException(status_code=422, detail=f"Неизвестный тариф: {body.plan_code}")
    plan = get_plan(body.plan_code)
    if plan.price_on_request:
        raise HTTPException(
            status_code=409,
            detail=(f"Тариф «{plan.name}» не оплачивается в продукте: его условия "
                    "согласуются отдельно, и назначает его платформа. Свяжитесь с нами — "
                    "автоматической заявки здесь нет."))
    _ensure_self_service_months(body.months)
    if body.auto_renew:
        if plan.price_rub <= 0:
            raise HTTPException(status_code=422,
                                detail="Бесплатный тариф не продлевают оплатой — "
                                       "автопродлению нечего списывать.")
        unavailable = billing.auto_renew_unavailable(provider)
        if unavailable:
            raise HTTPException(status_code=409, detail=unavailable)
    result = provider.start_checkout(db, org_id, plan, body.return_url, user.email,
                                     months=body.months, auto_renew=body.auto_renew)
    amount = billing.checkout_amount(plan, body.months)
    # Смена тарифа — деньги и квоты организации: событие журнала наравне с участниками.
    # Согласие на автопродление записано **здесь, с именем** давшего его: включит
    # автопродление подтверждение провайдера, у которого автора нет.
    crud.log_action(db, org_id, user, "billing.checkout", entity_type="organization",
                    entity_id=org_id, entity_name=plan.code,
                    details=("активирован сразу" if result.activated else "ожидает оплаты")
                    + f"; {body.months} мес., {amount} ₽"
                    + ("; с согласием на автопродление" if body.auto_renew else ""))
    if result.activated:
        # Событие — только на **состоявшейся** оплате: «начал платить» и «заплатил» в
        # одной воронке это разные шаги, и путать их значит завысить конверсию.
        usage.record(db, event="billing.paid", org_id=org_id, email=user.email,
                     context={"plan": plan.code})
    return CheckoutResponse(activated=result.activated, payment_id=result.payment_id,
                            confirmation_url=result.confirmation_url)


def _ensure_self_service_months(months: int) -> None:
    if months not in billing.SELF_SERVICE_MONTHS:
        raise HTTPException(
            status_code=422,
            detail=("В продукте оплачивают месяц или год (12 месяцев). Другой срок — "
                    "оплата по счёту: назначение тарифа сделает платформа."))


@router.get("/organizations/{org_id}/billing/quote", response_model=CheckoutQuoteOut)
def checkout_quote(plan_code: str, months: int = 1,
                   org_id: str = Depends(require_org_permission(Perm.BILLING_MANAGE)),
                   provider: PaymentProvider = Depends(get_payment_provider),
                   db: Session = Depends(get_db)) -> CheckoutQuoteOut:
    """Сколько заплатить и до какого дня будет оплачено — **до** оплаты (G5).

    Теми же функциями, что и сама оплата: продление того же тарифа продолжает период,
    переход на другой начинает новый — и тогда названо, сколько дней прежнего пропадёт.
    """
    if not is_valid_plan(plan_code):
        raise HTTPException(status_code=422, detail=f"Неизвестный тариф: {plan_code}")
    _ensure_self_service_months(months)
    plan = get_plan(plan_code)
    q = billing.quote(db, org_id, plan, months)
    unavailable = billing.auto_renew_unavailable(provider)
    return CheckoutQuoteOut(
        plan_code=plan.code, plan_name=plan.name, months=q.months, amount_rub=q.amount_rub,
        full_price_rub=q.full_price_rub, free_months=q.free_months,
        starts_at=q.starts_at, ends_at=q.ends_at, continues=q.continues,
        lost_days=q.lost_days, auto_renew_available=unavailable is None,
        auto_renew_unavailable_reason=unavailable or "")


@router.delete("/organizations/{org_id}/billing/auto-renew", response_model=SubscriptionOut)
def disable_auto_renew(product: str = "business",
                       org_id: str = Depends(require_org_permission(Perm.BILLING_MANAGE)),
                       user: User = Depends(current_user),
                       provider: PaymentProvider = Depends(get_payment_provider),
                       db: Session = Depends(get_db)) -> SubscriptionOut:
    """Выключить автопродление — в любой момент, и сохранённый способ забывается (G5).

    Забывается идентификатор способа у провайдера, а не только флаг: включить обратно
    можно лишь новой оплатой с отметкой согласия. Списание, которое провайдер уже
    получил, этим не отменяется — если оно пройдёт, период продлится; журнал говорит
    об этом, чтобы «я же выключил» не спорило с выпиской.
    """
    if product not in PRODUCTS:
        raise HTTPException(status_code=422, detail=f"Неизвестный продукт: {product}")
    sub = crud.get_subscription(db, org_id, product)
    if sub is not None and sub.auto_renew:
        method = sub.payment_method_title
        in_flight = (crud.open_renewal_payment(db, org_id, sub.current_period_end)
                     if sub.current_period_end is not None else None)
        crud.forget_auto_renew(sub)
        sub.renew_error = ""
        db.commit()
        crud.log_action(db, org_id, user, "billing.auto_renew_off",
                        entity_type="organization", entity_id=org_id,
                        entity_name=sub.plan_code,
                        details=f"{product}: выключено участником, способ «{method}» забыт"
                        + ("; списание, уже отправленное провайдеру, этим не отменено"
                           if in_flight is not None else ""))
    return _subscription_out(db, org_id, product, provider)


# --- Закрывающие документы (G6) ---

def document_out(doc) -> BillingDocumentOut:
    return BillingDocumentOut(id=doc.id, kind=doc.kind, number=doc.number,
                              doc_date=doc.doc_date, title=closing_docs.title(doc),
                              plan_name=doc.plan_name, months=doc.months,
                              amount_rub=doc.amount_rub, period_start=doc.period_start,
                              period_end=doc.period_end)


def _organization(db: Session, org_id: str):
    org = crud.get_organization(db, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Организация не найдена")
    return org


def _requisites_out(org) -> BuyerRequisitesOut:
    return BuyerRequisitesOut(legal_name=org.legal_name, inn=org.inn, kpp=org.kpp,
                              legal_address=org.legal_address,
                              problems=closing_docs.buyer_problems(org))


@router.get("/organizations/{org_id}/billing/requisites", response_model=BuyerRequisitesOut)
def get_requisites(org_id: str = Depends(require_membership),
                   db: Session = Depends(get_db)) -> BuyerRequisitesOut:
    """Реквизиты организации для счетов и актов — и что с ними не так."""
    return _requisites_out(_organization(db, org_id))


@router.put("/organizations/{org_id}/billing/requisites", response_model=BuyerRequisitesOut)
def update_requisites(body: BuyerRequisitesIn,
                      org_id: str = Depends(require_org_permission(Perm.BILLING_MANAGE)),
                      user: User = Depends(current_user),
                      db: Session = Depends(get_db)) -> BuyerRequisitesOut:
    """Сохранить реквизиты целиком. Опечатка в ИНН **не отклоняется** — сохраняется и
    называется: исправлять её человеку, а документ с ней не сформируется."""
    org = _organization(db, org_id)
    org.legal_name = body.legal_name.strip()
    org.inn = body.inn[:12]
    org.kpp = body.kpp[:9]
    org.legal_address = body.legal_address.strip()
    db.commit()
    crud.log_action(db, org_id, user, "org.requisites_update", entity_type="organization",
                    entity_id=org_id, entity_name=org.name,
                    details=f"{org.legal_name or '—'}, ИНН {org.inn or '—'}")
    return _requisites_out(org)


@router.get("/organizations/{org_id}/billing/documents", response_model=BillingDocumentsOut)
def list_billing_documents(org_id: str = Depends(require_membership),
                           db: Session = Depends(get_db)) -> BillingDocumentsOut:
    """Счета и акты организации — и акты, которых ещё нет, с причиной (G6)."""
    org = _organization(db, org_id)
    ready = not closing_docs.seller_problems()
    upcoming = closing_docs.upcoming_acts(db, org, datetime.now(timezone.utc))
    return BillingDocumentsOut(
        documents=[document_out(d) for d in closing_docs.list_documents(db, org_id)],
        upcoming=[UpcomingActOut(payment_id=u.payment_id, paid_at=u.paid_at,
                                 plan_name=u.plan_name, amount_rub=u.amount_rub,
                                 act_date=u.act_date, state=u.state, reason=u.reason)
                  for u in upcoming],
        seller_ready=ready, seller_note="" if ready else closing_docs.SELLER_NOT_READY,
        not_issued=closing_docs.NOT_ISSUED)


@router.post("/organizations/{org_id}/billing/invoices", response_model=BillingDocumentOut)
def create_invoice(body: InvoiceRequest,
                   org_id: str = Depends(require_org_permission(Perm.BILLING_MANAGE)),
                   user: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> BillingDocumentOut:
    """Счёт на оплату тарифа по безналу — по запросу клиента (G6).

    Открыт и в режиме чтения при неоплате: счёт — это способ заплатить, и закрыть его
    неплательщику значило бы запереть его в неоплате.
    """
    if not is_valid_plan(body.plan_code):
        raise HTTPException(status_code=422, detail=f"Неизвестный тариф: {body.plan_code}")
    org = _organization(db, org_id)
    try:
        doc = closing_docs.create_invoice(db, org, get_plan(body.plan_code), body.months,
                                          requested_by=user.email,
                                          today=datetime.now(timezone.utc).date())
    except closing_docs.DocumentRefused as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from exc
    crud.log_action(db, org_id, user, "billing.invoice", entity_type="billing_document",
                    entity_id=doc.id, entity_name=closing_docs.title(doc),
                    details=f"{doc.plan_name}, {doc.months} мес., {doc.amount_rub} ₽")
    return document_out(doc)


@router.get("/organizations/{org_id}/billing/documents/{doc_id}/docx")
def download_billing_document(doc_id: str, org_id: str = Depends(require_membership),
                              user: User = Depends(current_user),
                              db: Session = Depends(get_db)) -> Response:
    """Документ в DOCX — из его снимка. Выгрузка пишется в журнал, как любая выгрузка."""
    doc = closing_docs.get_document(db, org_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    content = build_document_docx(doc)
    crud.log_action(db, org_id, user, "billing.document_download",
                    entity_type="billing_document", entity_id=doc.id,
                    entity_name=closing_docs.title(doc), details="DOCX")
    ascii_name = f"{'invoice' if doc.kind == 'invoice' else 'act'}-{doc.number}-{doc.year}.docx"
    return Response(content=content, media_type=DOCX_MIME, headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; "
                               f"filename*=UTF-8''{quote(closing_docs.title(doc) + '.docx')}"})


@router.post("/billing/webhook/yookassa")
async def yookassa_webhook(request: Request,
                           provider: PaymentProvider = Depends(get_payment_provider),
                           db: Session = Depends(get_db)) -> dict:
    """Вебхук ЮKassa: активирует тариф по факту успешной оплаты (идемпотентно)."""
    event = await request.json()
    provider.handle_webhook(db, event)
    return {"status": "ok"}
