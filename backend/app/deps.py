"""Общие зависимости FastAPI: текущий пользователь и организация.

С 6.3 запросы аутентифицируются по JWT (``Authorization: Bearer``). Организация запроса
выводится из членства пользователя; необязательный заголовок ``X-Organization-Id``
позволяет выбрать организацию, если пользователь состоит в нескольких.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import crud
from .access import WRITE_PERMS, restriction_for
from .database import get_db, set_tenant
from .db_models import Membership, User
from .rbac import Perm, has_permission
from .security import decode_token

_bearer = HTTPBearer(auto_error=True)


#: Как часто отмечается присутствие участника. Отметка на каждый запрос превратила бы
#: таблицу членства в счётчик обращений и добавила бы запись к каждому чтению; для
#: вопроса «работает ли человек в организации» часа более чем достаточно.
SEEN_INTERVAL = timedelta(hours=1)


def _ensure_active(membership: Membership | None,
                   db: Session | None = None) -> Membership | None:
    """Проходная точка членства: отказать приостановленному и отметить присутствие.

    Отказ **403, а не 401**: токен действителен и человек тот самый, а 401 отправил бы
    его на экран входа — и он решил бы, что ошибся паролем. Причина идёт в ответе, чтобы
    участник знал, к кому идти, а не гадал.

    Проверка живёт здесь, а не в каждом эндпоинте: через эти зависимости проходит **любой**
    запрос к данным организации, поэтому забыть её нельзя. Отсюда же и мгновенность отзыва
    — членство читается из базы на каждом запросе, и выданный ранее токен не помогает.

    По той же причине здесь и отметка присутствия (A3): другого места, через которое
    гарантированно проходит работа с организацией, нет — а собранная в стороне отметка
    рано или поздно разошлась бы с тем, кто на самом деле работал.
    """
    if membership is not None and membership.blocked_at is not None:
        reason = membership.block_reason or "причина не указана"
        raise HTTPException(status_code=403,
                            detail=f"Доступ в организацию приостановлен: {reason}")
    if membership is not None and db is not None:
        now = datetime.now(timezone.utc)
        seen = membership.last_seen_at
        if seen is not None and seen.tzinfo is None:      # SQLite отдаёт наивное время
            seen = seen.replace(tzinfo=timezone.utc)
        if seen is None or now - seen >= SEEN_INTERVAL:
            membership.last_seen_at = now
            db.commit()
    return membership


def account_blocked_detail(user: User) -> str:
    """Текст отказа заблокированной учётной записи — один на все двери (B2).

    Блокировка учётной записи действует **на все организации сразу**, в отличие от
    приостановки членства (A1): она про человека, а не про его место в одной компании.
    Причина называется, чтобы человек знал, к кому идти; отказ — 403, а не 401, по тому
    же доводу, что и в A1: токен действителен, и экран входа отправил бы его искать
    ошибку в пароле.
    """
    reason = user.block_reason or "причина не указана"
    return f"Учётная запись заблокирована платформой: {reason}"


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
    if user.blocked_at is not None:
        # Проверка здесь, а не в каждом маршруте: через эту зависимость проходит любой
        # запрос платформы, включая служебный контур. Отзыв мгновенный по той же причине,
        # что и в A1 — учётная запись читается из базы на каждом запросе.
        raise HTTPException(status_code=403, detail=account_blocked_detail(user))
    return user


def require_staff(user: User = Depends(current_user)) -> User:
    """Сотрудник платформы (ADMIN-DECOMPOSITION.md, B1).

    Отдельная ось власти: признак **не выводится** из роли в организации и роль из него
    не выводится. Владелец крупного клиента не становится сотрудником платформы, а
    сотрудник платформы не получает прав в организациях, где не состоит, — служебные
    маршруты и клиентские не пересекаются нигде, кроме этой зависимости.

    Отказ — 403 с названной причиной, а не 404: прятать существование служебного контура
    смысла нет (он описан в документации), а молчаливый «не найдено» отправил бы своего
    же сотрудника искать опечатку в адресе вместо недостающего признака.
    """
    if not user.is_staff:
        raise HTTPException(status_code=403,
                            detail="Служебный раздел платформы: нужен признак сотрудника")
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
        _ensure_active(by_org[x_organization_id], db)
        org_id = x_organization_id
    else:
        # Организация по умолчанию — первая **действующая**: приостановка в одной
        # организации не должна запирать человека в остальных, где он работает.
        active = [m for m in memberships if m.blocked_at is None]
        if not active:
            _ensure_active(memberships[0], db)   # все приостановлены — назвать причину
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
    _ensure_active(membership, db)
    return org_id


def _ensure_not_restricted(db: Session, org_id: str, perm: Perm, product: str) -> None:
    """Режим чтения и выгрузки: закрыть правку, оставив просмотр (B2).

    Проверка живёт рядом с проверкой права — в одном месте на все маршруты — и опирается
    на **множество прав**, а не на список эндпоинтов: список пришлось бы дополнять при
    каждом новом маршруте, и однажды его забыли бы дополнить.
    """
    if perm not in WRITE_PERMS:
        return
    restriction = restriction_for(db, org_id, product)
    if restriction is not None:
        raise HTTPException(status_code=403, detail=restriction.detail)


def require_permission(perm: Perm, product: str = "business"):
    """Фабрика зависимостей: требовать право ``perm`` в текущей организации (из членства).

    Для проектов: организация выводится из ``current_org_id``. Отдаёт ``organization_id``.

    ``product`` называет, чья подписка отвечает за маршрут: у продуктов она своя, и
    просроченный «Аудит» не имеет отношения к оплаченному «Элит».
    """

    def dependency(
        org_id: str = Depends(current_org_id),
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> str:
        membership = _ensure_active(crud.get_membership(db, org_id, user.id), db)
        if not has_permission(membership.role if membership else None, perm):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        _ensure_not_restricted(db, org_id, perm, product)
        return org_id

    return dependency


def require_org_permission(perm: Perm, product: str = "business"):
    """Фабрика зависимостей: требовать право ``perm`` в организации **из пути** (``org_id``)."""

    def dependency(
        org_id: str,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> str:
        membership = _ensure_active(crud.get_membership(db, org_id, user.id), db)
        if not has_permission(membership.role if membership else None, perm):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        _ensure_not_restricted(db, org_id, perm, product)
        return org_id

    return dependency
