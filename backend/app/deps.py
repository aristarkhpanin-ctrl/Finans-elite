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
from .database import get_db, set_tenant
from .db_models import Membership, User
from .rbac import Perm, has_permission
from .security import decode_token

_bearer = HTTPBearer(auto_error=True)


def _ensure_active(membership: Membership | None) -> Membership | None:
    """Приостановленное членство — отказ с названной причиной (A1).

    Отказ **403, а не 401**: токен действителен и человек тот самый, а 401 отправил бы
    его на экран входа — и он решил бы, что ошибся паролем. Причина идёт в ответе, чтобы
    участник знал, к кому идти, а не гадал.

    Проверка живёт здесь, а не в каждом эндпоинте: через эти зависимости проходит **любой**
    запрос к данным организации, поэтому забыть её нельзя. Отсюда же и мгновенность отзыва
    — членство читается из базы на каждом запросе, и выданный ранее токен не помогает.
    """
    if membership is not None and membership.blocked_at is not None:
        reason = membership.block_reason or "причина не указана"
        raise HTTPException(status_code=403,
                            detail=f"Доступ в организацию приостановлен: {reason}")
    return membership


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
    by_org = {m.organization_id: m for m in memberships}
    if x_organization_id is not None:
        if x_organization_id not in by_org:
            raise HTTPException(status_code=403, detail="Нет доступа к организации")
        _ensure_active(by_org[x_organization_id])
        org_id = x_organization_id
    else:
        # Организация по умолчанию — первая **действующая**: приостановка в одной
        # организации не должна запирать человека в остальных, где он работает.
        active = [m for m in memberships if m.blocked_at is None]
        if not active:
            _ensure_active(memberships[0])   # все приостановлены — назвать причину
        org_id = active[0].organization_id
    set_tenant(db, org_id)  # RLS: изоляция арендатора на уровне БД (PostgreSQL)
    return org_id


def require_membership(
    org_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> str:
    """Проверить, что пользователь — участник организации из пути."""
    membership = crud.get_membership(db, org_id, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="Нет доступа к организации")
    _ensure_active(membership)
    return org_id


def require_permission(perm: Perm):
    """Фабрика зависимостей: требовать право ``perm`` в текущей организации (из членства).

    Для проектов: организация выводится из ``current_org_id``. Отдаёт ``organization_id``.
    """

    def dependency(
        org_id: str = Depends(current_org_id),
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> str:
        membership = _ensure_active(crud.get_membership(db, org_id, user.id))
        if not has_permission(membership.role if membership else None, perm):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return org_id

    return dependency


def require_org_permission(perm: Perm):
    """Фабрика зависимостей: требовать право ``perm`` в организации **из пути** (``org_id``)."""

    def dependency(
        org_id: str,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> str:
        membership = _ensure_active(crud.get_membership(db, org_id, user.id))
        if not has_permission(membership.role if membership else None, perm):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return org_id

    return dependency
