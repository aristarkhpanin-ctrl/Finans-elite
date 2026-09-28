"""Ключи доступа к API организации (ADMIN-DECOMPOSITION.md D5; OPEN-DECISIONS §3).

Ключ принадлежит организации и читает её данные: выгрузка показателей в BI, отчёт в 1С,
свод портфеля проектов. **Записывать он тоже умеет — если это выдали при выпуске**, и
тогда автором записи становится человек, выпустивший ключ, а ключ идёт пометкой в той же
записи журнала. Что именно ключу можно и чего нельзя — в `apikeys.ALLOWED_PERMS`.

Управляет ключами тот, кто отвечает за организацию (`org.manage`): ключ — дверь в её
данные, и заводить её должен тот же, кто заводит участников. Теперь у этого есть второй
смысл: ключ работает от имени выпустившего и гаснет вместе с ним.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import apikeys, crud
from ..database import get_db
from ..db_models import ApiKey, User
from ..deps import current_user, require_membership, require_org_permission
from ..rbac import Perm
from ..schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut, ApiKeyScopeOut

router = APIRouter(prefix="/api/v1/organizations", tags=["api-keys"])

#: Что умеет читающий ключ — текстом, который едет к человеку вместе с ключом.
SCOPE_NOTE = (
    "Ключ читает данные организации и запускает расчёт: проекты, дела, отчёты, выгрузки. "
    "Изменять модели, управлять участниками и тарифом этим ключом нельзя. "
    "Передавайте его заголовком: Authorization: Bearer <ключ>."
)

#: То же — про ключ, которому выдали запись. Разница названа целиком: и что он может, и
#: чьим именем это будет подписано, и когда он перестанет работать.
WRITE_NOTE = (
    "Ключ читает данные организации, запускает расчёт и **создаёт и правит модели** "
    "проектов и дел. Удалять модели, писать в обсуждении, управлять участниками и "
    "тарифом им нельзя. В журнале такие правки записаны на того, кто выпустил ключ, с "
    "пометкой о ключе — и ключ перестаёт работать, как только этот человек уходит из "
    "организации. Передавайте его заголовком: Authorization: Bearer <ключ>."
)


def _out(key: ApiKey) -> ApiKeyOut:
    perms = apikeys.effective_perms(key.scopes)
    return ApiKeyOut(
        id=key.id, name=key.name, masked=apikeys.masked(key.prefix),
        created_by=key.created_by, created_at=key.created_at,
        last_used_at=key.last_used_at, revoked=key.revoked_at is not None,
        revoked_at=key.revoked_at, revoked_by=key.revoked_by,
        scopes=sorted(p.value for p in perms),
        writes=bool(perms & apikeys.WRITE_PERMS),
        # Автор ключа — он же автор его записей. Потерянный автор не прячется: ключ уже
        # не работает, и список обязан говорить почему, а не показывать живую строку.
        author_gone=key.created_by_id is None,
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
    """Выпустить ключ. Секрет показывается **один раз** — платформа его не хранит.

    Права выбираются здесь и больше не меняются: ключ, права которого правят на ходу,
    означает, что владелец чужого сервера однажды получит больше, чем ему выдавали, и
    никто этого не заметит. Нужно другое — выпускается другой ключ.
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=422,
            detail="У ключа должно быть имя: через год список безымянных ключей означает, "
                   "что отозвать можно только все сразу.")
    unknown = apikeys.unknown_scopes(body.scopes or [])
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(f"Таких прав у ключа не бывает: {', '.join(unknown)}. Ключу можно "
                    f"выдать только: {', '.join(sorted(p.value for p in apikeys.ALLOWED_PERMS))}."))
    if crud.count_active_api_keys(db, org_id) >= apikeys.MAX_KEYS_PER_ORG:
        raise HTTPException(
            status_code=409,
            detail=f"Действующих ключей уже {apikeys.MAX_KEYS_PER_ORG}. Отзовите лишние: "
                   "список, в котором никто не помнит, какой ключ где живёт, опаснее "
                   "отсутствия ключей.")
    fresh = apikeys.generate()
    perms = apikeys.effective_perms(body.scopes)
    key = crud.create_api_key(db, org_id, name=name, prefix=fresh.prefix,
                              fingerprint=fresh.fingerprint, created_by=actor.email,
                              created_by_id=actor.id,
                              scopes=sorted(p.value for p in perms))
    writes = bool(perms & apikeys.WRITE_PERMS)
    # Права ключа — в журнале, а не только в списке: «выпустили ключ» и «выпустили ключ,
    # который правит модели» — разные события для того, кто читает журнал через полгода.
    crud.log_action(db, org_id, actor, "apikey.create", entity_type="api_key",
                    entity_id=key.id, entity_name=name,
                    details=(f"{apikeys.masked(fresh.prefix)} · "
                             + ("чтение и запись моделей" if writes else "только чтение")))
    return ApiKeyCreated(key=_out(key), token=fresh.token,
                         scope_note=WRITE_NOTE if writes else SCOPE_NOTE)


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


@router.get("/{org_id}/api-keys/scope", response_model=ApiKeyScopeOut)
def key_scope(org_id: str = Depends(require_membership)) -> ApiKeyScopeOut:
    """Что ключу можно — перечнем прав, а не обещанием на словах.

    Два списка, а не один: «есть всегда» и «можно выдать» — разные ответы, и экран, где
    они слиты, заставляет гадать, что именно выбирают при выпуске.
    """
    return ApiKeyScopeOut(
        always=sorted(p.value for p in apikeys.READ_PERMS),
        grantable=sorted(p.value for p in apikeys.WRITE_PERMS),
        note=("Ключ всегда читает и считает. Право создавать и править модели выдаётся "
              "при выпуске: такие правки записаны в журнале на того, кто выпустил ключ, "
              "и ключ перестаёт работать, когда этот человек уходит из организации. "
              "Удаление моделей и реплики в обсуждении ключом недоступны никогда."),
    )
