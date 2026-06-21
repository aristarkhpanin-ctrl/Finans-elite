"""Тарифы, подписка и платежи (биллинг, 6.5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import billing, crud
from ..billing import PaymentProvider, get_payment_provider
from ..database import get_db
from ..db_models import User
from ..deps import current_user, require_membership, require_org_permission
from ..plans import PLANS, get_plan, is_valid_plan
from ..rbac import Perm
from ..schemas import (
    CheckoutRequest,
    CheckoutResponse,
    PlanOut,
    SubscriptionOut,
    SubscriptionUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
def list_plans() -> list[PlanOut]:
    """Каталог доступных тарифов (публично)."""
    return [
        PlanOut(code=p.code, name=p.name, price_rub=p.price_rub,
                max_projects=p.max_projects, max_members=p.max_members)
        for p in PLANS.values()
    ]


def _subscription_out(db: Session, org_id: str) -> SubscriptionOut:
    sub = crud.get_subscription(db, org_id)
    plan = billing.current_plan(db, org_id)
    return SubscriptionOut(
        plan_code=plan.code,
        plan_name=plan.name,
        status=sub.status if sub else "active",
        current_period_end=sub.current_period_end if sub else None,
        max_projects=plan.max_projects,
        max_members=plan.max_members,
        used_projects=crud.count_projects(db, org_id),
        used_members=crud.count_members(db, org_id),
    )


@router.get("/organizations/{org_id}/subscription", response_model=SubscriptionOut)
def get_subscription(org_id: str = Depends(require_membership),
                     db: Session = Depends(get_db)) -> SubscriptionOut:
    """Текущая подписка организации (с использованием квот)."""
    return _subscription_out(db, org_id)


@router.post("/organizations/{org_id}/subscription", response_model=SubscriptionOut)
def change_subscription(body: SubscriptionUpdate,
                        org_id: str = Depends(require_org_permission(Perm.BILLING_MANAGE)),
                        db: Session = Depends(get_db)) -> SubscriptionOut:
    """Прямая смена тарифа без платежа (право billing.manage; ручной/админский путь)."""
    if not is_valid_plan(body.plan_code):
        raise HTTPException(status_code=422, detail=f"Неизвестный тариф: {body.plan_code}")
    crud.set_plan(db, org_id, body.plan_code)
    return _subscription_out(db, org_id)


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
