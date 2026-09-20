"""Тарифы, подписка и платежи (биллинг, 6.5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import billing, crud, usage
from ..billing import PaymentProvider, get_payment_provider
from ..database import get_db
from ..db_models import User
from ..deps import current_user, require_membership, require_org_permission
from ..plans import PLANS, UNIT_NAME, get_plan, is_valid_plan, product_of
from ..rbac import Perm
from ..schemas import (
    CheckoutRequest,
    CheckoutResponse,
    PlanOut,
    SubscriptionOut,
    SubscriptionUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["billing"])


def _plan_out(p) -> PlanOut:
    return PlanOut(code=p.code, product=p.product, name=p.name, price_rub=p.price_rub,
                   price_on_request=p.price_on_request, max_units=p.max_units,
                   unit_name=UNIT_NAME.get(p.product, "объектов"),
                   max_members=p.max_members)


@router.get("/plans", response_model=list[PlanOut])
def list_plans(product: str | None = None) -> list[PlanOut]:
    """Каталог тарифов (публично); ``product`` — только тарифы одного продукта."""
    return [_plan_out(p) for p in PLANS.values() if product is None or p.product == product]


def _subscription_out(db: Session, org_id: str, product: str = "business") -> SubscriptionOut:
    sub = crud.get_subscription(db, org_id, product)
    plan = billing.current_plan(db, org_id, product)
    used = (crud.count_audit_subjects(db, org_id) if product == "audit"
            else crud.count_projects(db, org_id))
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
    )


@router.get("/organizations/{org_id}/subscription", response_model=SubscriptionOut)
def get_subscription(product: str = "business",
                     org_id: str = Depends(require_membership),
                     db: Session = Depends(get_db)) -> SubscriptionOut:
    """Подписка организации на продукт (с использованием квот)."""
    return _subscription_out(db, org_id, product)


@router.get("/organizations/{org_id}/subscriptions", response_model=list[SubscriptionOut])
def get_subscriptions(org_id: str = Depends(require_membership),
                      db: Session = Depends(get_db)) -> list[SubscriptionOut]:
    """Подписки организации по всем продуктам — их столько же, сколько продуктов."""
    from ..plans import PRODUCTS
    return [_subscription_out(db, org_id, p) for p in PRODUCTS]


@router.post("/organizations/{org_id}/subscription", response_model=SubscriptionOut)
def change_subscription(body: SubscriptionUpdate,
                        org_id: str = Depends(require_org_permission(Perm.BILLING_MANAGE)),
                        user: User = Depends(current_user),
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
    # ``paid=True`` с бесплатным тарифом **стирает** чужой срок: уходя с платного,
    # организация не должна тащить за собой его дату (см. `crud.set_plan`).
    crud.set_plan(db, org_id, body.plan_code, product=product, period_end=None, paid=True)
    crud.log_action(db, org_id, user, "billing.plan_change", entity_type="organization",
                    entity_id=org_id, entity_name=body.plan_code, details=product)
    return _subscription_out(db, org_id, product)


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
    result = provider.start_checkout(db, org_id, plan, body.return_url, user.email)
    # Смена тарифа — деньги и квоты организации: событие журнала наравне с участниками.
    crud.log_action(db, org_id, user, "billing.checkout", entity_type="organization",
                    entity_id=org_id, entity_name=plan.code,
                    details="активирован сразу" if result.activated else "ожидает оплаты")
    if result.activated:
        # Событие — только на **состоявшейся** оплате: «начал платить» и «заплатил» в
        # одной воронке это разные шаги, и путать их значит завысить конверсию.
        usage.record(db, event="billing.paid", org_id=org_id, email=user.email,
                     context={"plan": plan.code})
    return CheckoutResponse(activated=result.activated, payment_id=result.payment_id,
                            confirmation_url=result.confirmation_url)


@router.post("/billing/webhook/yookassa")
async def yookassa_webhook(request: Request,
                           provider: PaymentProvider = Depends(get_payment_provider),
                           db: Session = Depends(get_db)) -> dict:
    """Вебхук ЮKassa: активирует тариф по факту успешной оплаты (идемпотентно)."""
    event = await request.json()
    provider.handle_webhook(db, event)
    return {"status": "ok"}
