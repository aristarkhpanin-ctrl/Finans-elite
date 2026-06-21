"""REST-эндпоинты организаций и членства (6.2 + защита аутентификацией 6.3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..db_models import User
from ..deps import current_user, require_membership
from ..schemas import (
    MemberCreate,
    MemberOut,
    OrganizationCreate,
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


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(org_id: str = Depends(require_membership),
                     db: Session = Depends(get_db)) -> OrganizationOut:
    org = crud.get_organization(db, org_id)
    return OrganizationOut(id=org.id, name=org.name, created_at=org.created_at)


@router.post("/{org_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(body: MemberCreate, org_id: str = Depends(require_membership),
               db: Session = Depends(get_db)) -> MemberOut:
    """Добавить участника организации (создаёт пользователя по email при необходимости)."""
    membership = crud.add_member(db, org_id, body.email, body.full_name, body.role)
    user = crud.get_user_by_email(db, body.email)
    return MemberOut(user_id=user.id, email=user.email, full_name=user.full_name,
                     role=membership.role)


@router.get("/{org_id}/members", response_model=list[MemberOut])
def list_members(org_id: str = Depends(require_membership),
                 db: Session = Depends(get_db)) -> list[MemberOut]:
    return [
        MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, role=m.role)
        for m, u in crud.list_members(db, org_id)
    ]
