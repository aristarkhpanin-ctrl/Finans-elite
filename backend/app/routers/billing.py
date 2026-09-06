"""Тарифы, подписка и платежи (биллинг, 6.5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import billing, crud
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
                        db: Session = Depends(get_db)) -> SubscriptionOut:
    """Прямая смена тарифа без платежа (право billing.manage; ручной/админский путь)."""
    if not is_valid_plan(body.plan_code):
        raise HTTPException(status_code=422, detail=f"Неизвестный тариф: {body.plan_code}")
    # Продукт выводится из кода тарифа, а не приходит отдельным полем: два источника
    # правды разошлись бы, и организация получила бы тариф «Аудита» в подписке «Элит».
    product = product_of(body.plan_code)
    crud.set_plan(db, org_id, body.plan_code, product=product)
    return _subscription_out(db, org_id, product)


@router.post("/organizations/{org_id}/billing/checkout", response_model=CheckoutResponse)
def checkout(body: CheckoutRequest,
             org_id: str = Depends(require_org_permission(Perm.BILLING_MANAGE)),
             user: User = Depends(current_user),
             provider: PaymentProvider = Depends(get_payment_provider),
             db: Session = Depends(get_db)) -> CheckoutResponse:
    """Инициировать смену тарифа через провайдера (ЮKassa — ссылка оплаты; ручной — сразу)."""
    if not is_valid_plan(body.plan_code):
        raise HTTPException(status_code=422, detail=f"Неизвестный тариф: {body.plan_code}")
    result = provider.start_checkout(db, org_id, get_plan(body.plan_code),
                                     body.return_url, user.email)
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
