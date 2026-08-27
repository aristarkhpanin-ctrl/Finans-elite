"""REST-эндпоинты организаций и членства (6.2 + аутентификация 6.3 + RBAC 6.4)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import billing, crud
from ..database import get_db
from ..db_models import User
from ..deps import current_user, require_membership, require_org_permission
from ..rbac import Perm, is_valid_role
from ..schemas import (
    AuditLogEntryOut,
    AuditLogPage,
    MemberCreate,
    MemberOut,
    MemberPatch,
    OrganizationCreate,
    OrganizationMembershipOut,
    OrganizationOut,
)
from ..security import create_invite_token

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
               actor: User = Depends(current_user),
               db: Session = Depends(get_db)) -> MemberOut:
    """Добавить участника (право member.manage). Создаёт пользователя по email при необходимости."""
    if not is_valid_role(body.role):
        raise HTTPException(status_code=422, detail=f"Недопустимая роль: {body.role}")
    # квота участников — только для нового члена (повторное добавление идемпотентно)
    existing = crud.get_user_by_email(db, body.email)
    if not (existing and crud.is_member(db, org_id, existing.id)):
        billing.ensure_member_quota(db, org_id)
    membership = crud.add_member(db, org_id, body.email, body.full_name, body.role)
    user = crud.get_user_by_email(db, body.email)
    crud.log_action(db, org_id, actor, "member.add", entity_type="member",
                    entity_id=user.id, entity_name=user.email,
                    details=f"роль: {membership.role}")
    # Приглашённому, у которого ещё нет пароля, нужен способ его завести. Почтовой
    # отправки у платформы нет, поэтому ссылка активации возвращается пригласившему —
    # он передаёт её лично. В списке участников токена нет: там он был бы вечным
    # пропуском в чужой аккаунт для всякого, кто видит состав организации.
    invite = None if user.hashed_password else create_invite_token(user.id)
    return MemberOut(user_id=user.id, email=user.email, full_name=user.full_name,
                     role=membership.role, invite_token=invite)


@router.get("/{org_id}/members", response_model=list[MemberOut])
def list_members(org_id: str = Depends(require_org_permission(Perm.MEMBER_READ)),
                 db: Session = Depends(get_db)) -> list[MemberOut]:
    return [
        MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, role=m.role)
        for m, u in crud.list_members(db, org_id)
    ]


def _member_or_404(db: Session, org_id: str, user_id: str):
    membership = crud.get_membership(db, org_id, user_id)
    if membership is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    return membership


@router.patch("/{org_id}/members/{user_id}", response_model=MemberOut)
def patch_member_role(user_id: str, body: MemberPatch,
                      org_id: str = Depends(require_org_permission(Perm.MEMBER_MANAGE)),
                      actor: User = Depends(current_user),
                      db: Session = Depends(get_db)) -> MemberOut:
    """Изменить роль участника (право member.manage; владельца понизить нельзя, B4)."""
    if not is_valid_role(body.role):
        raise HTTPException(status_code=422, detail=f"Недопустимая роль: {body.role}")
    membership = _member_or_404(db, org_id, user_id)
    if membership.role == "owner" and body.role != "owner":
        raise HTTPException(status_code=409, detail="Нельзя понизить владельца организации")
    was = membership.role
    updated = crud.set_membership_role(db, membership, body.role)
    user = crud.get_user(db, user_id)
    crud.log_action(db, org_id, actor, "member.role_change", entity_type="member",
                    entity_id=user.id, entity_name=user.email,
                    details=f"{was} → {updated.role}")
    return MemberOut(user_id=user.id, email=user.email, full_name=user.full_name, role=updated.role)


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(user_id: str,
                  org_id: str = Depends(require_org_permission(Perm.MEMBER_MANAGE)),
                  actor: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> None:
    """Удалить участника (право member.manage; нельзя удалить владельца и себя, B4)."""
    membership = _member_or_404(db, org_id, user_id)
    if membership.role == "owner":
        raise HTTPException(status_code=409, detail="Нельзя удалить владельца организации")
    if user_id == actor.id:
        raise HTTPException(status_code=409, detail="Нельзя удалить себя из организации")
    removed = crud.get_user(db, user_id)
    crud.remove_membership(db, membership)
    crud.log_action(db, org_id, actor, "member.remove", entity_type="member",
                    entity_id=user_id,
                    entity_name=removed.email if removed else user_id,
                    details=f"роль была: {membership.role}")


@router.get("/{org_id}/audit-log", response_model=AuditLogPage)
def read_audit_log(limit: int = 200, before: datetime | None = None,
                   org_id: str = Depends(require_org_permission(Perm.ORG_MANAGE)),
                   db: Session = Depends(get_db)) -> AuditLogPage:
    """Журнал действий организации (право org.manage): новые записи сверху.

    Только чтение. Ни PUT, ни DELETE у журнала нет и не будет: журнал, который можно
    поправить, не журнал. Срок хранения (5 лет, ARCHITECTURE §4) — политика эксплуатации,
    а не логика приложения: чистка кодом означала бы, что приложение умеет стирать
    собственные следы.
    """
    limit = max(1, min(limit, 500))
    entries = crud.list_audit_log(db, org_id, limit=limit, before=before)
    return AuditLogPage(
        entries=[AuditLogEntryOut(id=e.id, actor_email=e.actor_email, action=e.action,
                                  entity_type=e.entity_type, entity_id=e.entity_id,
                                  entity_name=e.entity_name, details=e.details,
                                  created_at=e.created_at) for e in entries],
        total=crud.count_audit_log(db, org_id),
    )
