"""Ключи доступа к API организации (ADMIN-DECOMPOSITION.md, D5).

Ключ принадлежит организации и **читает** её данные: выгрузка показателей в BI, отчёт в
1С, свод портфеля проектов. Запись ключом не делается — у записи в журнале есть автор, а
«модель изменил ключ» не автор; решение названо в :data:`deps.KEY_READ_ONLY` и в плане.

Управляет ключами тот, кто отвечает за организацию (`org.manage`): ключ — дверь в её
данные, и заводить её должен тот же, кто заводит участников.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import apikeys, crud
from ..database import get_db
from ..db_models import ApiKey, User
from ..deps import KEY_PERMS, current_user, require_membership, require_org_permission
from ..rbac import Perm
from ..schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

router = APIRouter(prefix="/api/v1/organizations", tags=["api-keys"])

#: Что ключ умеет — текстом, который едет к человеку вместе с ключом.
SCOPE_NOTE = (
    "Ключ читает данные организации и запускает расчёт: проекты, дела, отчёты, выгрузки. "
    "Изменять модели, управлять участниками и тарифом ключом нельзя — это делает человек. "
    "Передавайте его заголовком: Authorization: Bearer <ключ>."
)


def _out(key: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=key.id, name=key.name, masked=apikeys.masked(key.prefix),
        created_by=key.created_by, created_at=key.created_at,
        last_used_at=key.last_used_at, revoked=key.revoked_at is not None,
        revoked_at=key.revoked_at, revoked_by=key.revoked_by,
    )


@router.get("/{org_id}/api-keys", response_model=list[ApiKeyOut])
def list_keys(org_id: str = Depends(require_membership),
              db: Session = Depends(get_db)) -> list[ApiKeyOut]:
    """Ключи организации, новые сверху. Отозванные остаются в списке: исчезнувший ключ
    читался бы как никогда не существовавший, а он работал."""
    return [_out(k) for k in crud.list_api_keys(db, org_id)]


@router.post("/{org_id}/api-keys", response_model=ApiKeyCreated,
             status_code=status.HTTP_201_CREATED)
def create_key(body: ApiKeyCreate,
               org_id: str = Depends(require_org_permission(Perm.ORG_MANAGE)),
               actor: User = Depends(current_user),
               db: Session = Depends(get_db)) -> ApiKeyCreated:
    """Выпустить ключ. Секрет показывается **один раз** — платформа его не хранит."""
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=422,
            detail="У ключа должно быть имя: через год список безымянных ключей означает, "
                   "что отозвать можно только все сразу.")
    if crud.count_active_api_keys(db, org_id) >= apikeys.MAX_KEYS_PER_ORG:
        raise HTTPException(
            status_code=409,
            detail=f"Действующих ключей уже {apikeys.MAX_KEYS_PER_ORG}. Отзовите лишние: "
                   "список, в котором никто не помнит, какой ключ где живёт, опаснее "
                   "отсутствия ключей.")
    fresh = apikeys.generate()
    key = crud.create_api_key(db, org_id, name=name, prefix=fresh.prefix,
                              fingerprint=fresh.fingerprint, created_by=actor.email)
    crud.log_action(db, org_id, actor, "apikey.create", entity_type="api_key",
                    entity_id=key.id, entity_name=name,
                    details=apikeys.masked(fresh.prefix))
    return ApiKeyCreated(key=_out(key), token=fresh.token, scope_note=SCOPE_NOTE)


@router.delete("/{org_id}/api-keys/{key_id}", response_model=ApiKeyOut)
def revoke_key(key_id: str,
               org_id: str = Depends(require_org_permission(Perm.ORG_MANAGE)),
               actor: User = Depends(current_user),
               db: Session = Depends(get_db)) -> ApiKeyOut:
    """Отозвать ключ. Мгновенно: состояние читается из базы на каждом запросе."""
    key = crud.get_api_key(db, org_id, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Ключ не найден")
    revoked = crud.revoke_api_key(db, key, by=actor.email)
    crud.log_action(db, org_id, actor, "apikey.revoke", entity_type="api_key",
                    entity_id=key.id, entity_name=key.name,
                    details=apikeys.masked(key.prefix))
    return _out(revoked)


@router.get("/{org_id}/api-keys/scope", response_model=list[str])
def key_scope(org_id: str = Depends(require_membership)) -> list[str]:
    """Что ключ умеет — перечнем прав, а не обещанием на словах."""
    return sorted(p.value for p in KEY_PERMS)
