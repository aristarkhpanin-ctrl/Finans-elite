"""Общие зависимости FastAPI: текущий пользователь и организация.

С 6.3 запросы аутентифицируются по JWT (``Authorization: Bearer``). Организация запроса
выводится из членства пользователя; необязательный заголовок ``X-Organization-Id``
позволяет выбрать организацию, если пользователь состоит в нескольких.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import crud
from .database import get_db
from .db_models import User
from .security import decode_token

_bearer = HTTPBearer(auto_error=True)


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Текущий пользователь по токену доступа."""
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Недействительный токен")
    user = crud.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user


def current_org_id(
    user: User = Depends(current_user),
    x_organization_id: str | None = Header(default=None, alias="X-Organization-Id"),
    db: Session = Depends(get_db),
) -> str:
    """Текущая организация (арендатор) — по членству пользователя."""
    memberships = crud.list_user_memberships(db, user.id)
    if not memberships:
        raise HTTPException(status_code=400, detail="Пользователь не состоит в организации")
    org_ids = {m.organization_id for m in memberships}
    if x_organization_id is not None:
        if x_organization_id not in org_ids:
            raise HTTPException(status_code=403, detail="Нет доступа к организации")
        return x_organization_id
    return memberships[0].organization_id


def require_membership(
    org_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> str:
    """Проверить, что пользователь — участник организации из пути."""
    if not crud.is_member(db, org_id, user.id):
        raise HTTPException(status_code=403, detail="Нет доступа к организации")
    return org_id
