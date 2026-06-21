"""Общие зависимости FastAPI.

``current_org_id`` определяет арендатора текущего запроса. В 6.2 — по заголовку
``X-Organization-Id`` (временный шов); в 6.3 организация будет выводиться из
аутентифицированного пользователя (JWT), а заголовок убран.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import crud
from .database import get_db


def current_org_id(
    x_organization_id: str = Header(..., alias="X-Organization-Id"),
    db: Session = Depends(get_db),
) -> str:
    """Текущая организация (арендатор) по заголовку ``X-Organization-Id``."""
    if crud.get_organization(db, x_organization_id) is None:
        raise HTTPException(status_code=404, detail="Организация не найдена")
    return x_organization_id
