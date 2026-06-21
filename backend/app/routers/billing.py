"""Тарифы и подписка (биллинг, 6.5a)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import billing, crud
from ..database import get_db
from ..deps import require_membership, require_org_permission
from ..plans import PLANS, get_plan, is_valid_plan
from ..rbac import Perm
from ..schemas import PlanOut, SubscriptionOut, SubscriptionUpdate

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
    """Сменить тариф (право billing.manage). В 6.5a — без внешнего платежа."""
    if not is_valid_plan(body.plan_code):
        raise HTTPException(status_code=422, detail=f"Неизвестный тариф: {body.plan_code}")
    billing.provider.change_plan(db, org_id, body.plan_code)
    return _subscription_out(db, org_id)
