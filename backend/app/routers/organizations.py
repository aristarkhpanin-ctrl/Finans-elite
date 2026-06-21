"""REST-эндпоинты организаций и членства (6.2 + аутентификация 6.3 + RBAC 6.4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..db_models import User
from ..deps import current_user, require_membership, require_org_permission
from ..rbac import Perm, is_valid_role
from ..schemas import (
    MemberCreate,
    MemberOut,
    OrganizationCreate,
    OrganizationMembershipOut,
    OrganizationOut,
)

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(body: OrganizationCreate, user: User = Depends(current_user),
                        db: Session = Depends(get_db)) -> OrganizationOut:
    """Создать организацию; создатель становится её владельцем."""
    org = crud.create_organization(db, body.name)
    crud.add_membership(db, org.id, user.id, role="owner")
    return OrganizationOut(id=org.id, name=org.name, created_at=org.created_at)


@router.get("", response_model=list[OrganizationMembershipOut])
def my_organizations(user: User = Depends(current_user),
                     db: Session = Depends(get_db)) -> list[OrganizationMembershipOut]:
    """Организации текущего пользователя (с его ролью в каждой)."""
    return [
        OrganizationMembershipOut(id=org.id, name=org.name, role=role, created_at=org.created_at)
        for org, role in crud.list_user_organizations(db, user.id)
    ]


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(org_id: str = Depends(require_membership),
                     db: Session = Depends(get_db)) -> OrganizationOut:
    org = crud.get_organization(db, org_id)
    return OrganizationOut(id=org.id, name=org.name, created_at=org.created_at)


@router.post("/{org_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(body: MemberCreate,
               org_id: str = Depends(require_org_permission(Perm.MEMBER_MANAGE)),
               db: Session = Depends(get_db)) -> MemberOut:
    """Добавить участника (право member.manage). Создаёт пользователя по email при необходимости."""
    if not is_valid_role(body.role):
        raise HTTPException(status_code=422, detail=f"Недопустимая роль: {body.role}")
    membership = crud.add_member(db, org_id, body.email, body.full_name, body.role)
    user = crud.get_user_by_email(db, body.email)
    return MemberOut(user_id=user.id, email=user.email, full_name=user.full_name,
                     role=membership.role)


@router.get("/{org_id}/members", response_model=list[MemberOut])
def list_members(org_id: str = Depends(require_org_permission(Perm.MEMBER_READ)),
                 db: Session = Depends(get_db)) -> list[MemberOut]:
    return [
        MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, role=m.role)
        for m, u in crud.list_members(db, org_id)
    ]
