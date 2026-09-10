"""Служебный контур платформы: что мы видим о своих клиентах (ADMIN-DECOMPOSITION.md, B1).

Отдельный роутер, отдельная зависимость (:func:`deps.require_staff`), отдельный журнал.
Ни один клиентский маршрут прав оператора не получает, и ни один служебный не выдаёт
содержимого моделей: оператору видны метаданные — организации, состав, подписки, объёмы —
и не видно ни одного числа из проекта или дела (правило 6 плана). Иначе владелец SaaS
читает финансовые модели своих клиентов, то есть ровно то, чего клиент и опасается.

**Обхода изоляции арендатора здесь нет.** Служебные запросы к данным организации идут
через тот же ``set_tenant``, что и клиентские: оператор входит в организацию по очереди,
через ту же дверь, и выходит из неё явно (:func:`_as_tenant`). Отдельная роль в
PostgreSQL или политика с лазейкой дали бы контур, в котором RLS не действует, — и он
существовал бы ровно до первой ошибки в коде, которая направит туда клиентский запрос.

**Правило «журнал не пишет чтение» здесь имеет названное исключение.** Оно защищает
журнал от потока собственных просмотров участников; приход **постороннего** — событие,
которого клиент иначе не увидит вовсе. Поэтому визит в конкретную организацию пишется в
её журнал, а платформенные списки (все организации, поиск человека) — только в служебный:
иначе одно обновление экрана оператора оставило бы запись у каждого клиента сразу, и
сигнал «к нам приходили» утонул бы в шуме, который сам же и создаёт.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud
from ..database import clear_tenant, get_db, set_tenant
from ..db_models import User
from ..deps import require_staff
from ..plans import PRODUCTS, get_plan
from ..schemas import (
    AuditLogPage,
    StaffLogEntryOut,
    StaffLogPage,
    StaffOrgDetail,
    StaffOrgOut,
    StaffOrgPage,
    StaffSubscriptionOut,
    StaffUserOrgOut,
    StaffUserOut,
)
from .organizations import _log_entry_out, _member_out

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@contextmanager
def _as_tenant(db: Session, org_id: str) -> Iterator[None]:
    """Войти в организацию как арендатор и выйти из неё.

    Оставленный от предыдущей организации арендатор — открытая дверь в чужие данные,
    которую никто не заметит: следующий запрос той же сессии прочитал бы не то, что
    просил. Выход обязателен и потому оформлен контекстом, а не парой вызовов.
    """
    set_tenant(db, org_id)
    try:
        yield
    finally:
        clear_tenant(db)


def _subscriptions_out(db: Session, org_id: str) -> list[StaffSubscriptionOut]:
    """Оба продукта платформы, а не только оформленные подписки.

    Организация пользуется продуктом и на тарифе по умолчанию, подписки при этом нет
    вовсе. Показать только оформленные значило бы, что клиент с тремя делами выглядит
    не пользующимся «Аудитом»; статус ``none`` отличает «не оформлял» от «оформил
    бесплатный», и это разные разговоры с клиентом.
    """
    subs = {s.product: s for s in crud.list_subscriptions(db, org_id)}
    out = []
    for product in PRODUCTS:
        sub = subs.get(product)
        plan = get_plan(sub.plan_code if sub else None, product)
        out.append(StaffSubscriptionOut(
            product=product, plan_code=plan.code, plan_name=plan.name,
            status=sub.status if sub else "none",
            current_period_end=sub.current_period_end if sub else None))
    return out


def _org_out(db: Session, org) -> StaffOrgOut:
    """Метаданные организации. Объёмы считаются, стоя в её же дверях (RLS)."""
    with _as_tenant(db, org.id):
        volumes = crud.org_volumes(db, org.id)
    return StaffOrgOut(id=org.id, name=org.name, created_at=org.created_at,
                       subscriptions=_subscriptions_out(db, org.id), **volumes)


@router.get("/organizations", response_model=StaffOrgPage)
def list_organizations(q: str = "", limit: int = 50, offset: int = 0,
                       staff: User = Depends(require_staff),
                       db: Session = Depends(get_db)) -> StaffOrgPage:
    """Клиенты платформы: кто, с какого числа, на каком тарифе и сколько чего завёл.

    Пишется **только в служебный журнал**: список — это платформенный взгляд, а не визит
    к конкретному клиенту. Запись у каждого клиента при каждом обновлении экрана сделала
    бы их журналы нечитаемыми.
    """
    limit = max(1, min(limit, 200))
    orgs = crud.list_organizations(db, q=q, limit=limit, offset=offset)
    crud.log_staff_action(db, staff, "staff.orgs_list",
                          details=f"найдено: {len(orgs)}" + (f", отбор: {q}" if q else ""))
    return StaffOrgPage(organizations=[_org_out(db, o) for o in orgs],
                        total=crud.count_organizations(db, q=q))


@router.get("/organizations/{org_id}", response_model=StaffOrgDetail)
def get_organization(org_id: str, staff: User = Depends(require_staff),
                     db: Session = Depends(get_db)) -> StaffOrgDetail:
    """Карточка клиента: подписки, объёмы, состав.

    Визит пишется **в оба журнала** — в служебный и в журнал самой организации. Клиент
    обязан видеть, что к нему приходили, даже (и особенно) когда приходили мы.
    """
    org = crud.get_organization(db, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Организация не найдена")
    base = _org_out(db, org)
    members = [_member_out(m, u) for m, u in crud.list_members(db, org_id)]
    with _as_tenant(db, org_id):
        crud.log_action(db, org_id, staff, "staff.org_view", entity_type="organization",
                        entity_id=org_id, entity_name=org.name,
                        details="просмотр сотрудником платформы")
    crud.log_staff_action(db, staff, "staff.org_view", org_id=org_id, org_name=org.name)
    return StaffOrgDetail(**base.model_dump(), members_list=members)


@router.get("/organizations/{org_id}/audit-log", response_model=AuditLogPage)
def read_audit_log(org_id: str, limit: int = 200, actor: str = "", action: str = "",
                   since: datetime | None = None, until: datetime | None = None,
                   q: str = "", staff: User = Depends(require_staff),
                   db: Session = Depends(get_db)) -> AuditLogPage:
    """Журнал организации глазами оператора — тот же, что видит её администратор.

    Второго представления журнала не заводим: расхождение двух ответов на один вопрос
    («что у клиента происходило») пришлось бы разбирать в момент инцидента, то есть
    тогда, когда времени на это меньше всего.
    """
    org = crud.get_organization(db, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Организация не найдена")
    limit = max(1, min(limit, 500))
    f = {"actor": actor, "action": action, "since": since, "until": until, "q": q}
    with _as_tenant(db, org_id):
        entries = crud.list_audit_log(db, org_id, limit=limit, **f)
        page = AuditLogPage(entries=[_log_entry_out(e) for e in entries],
                            total=crud.count_audit_log(db, org_id, **f),
                            actors=crud.audit_log_actors(db, org_id),
                            actions=crud.audit_log_actions(db, org_id))
        crud.log_action(db, org_id, staff, "staff.audit_log_view",
                        entity_type="organization", entity_id=org_id, entity_name=org.name,
                        details="журнал прочитан сотрудником платформы")
    crud.log_staff_action(db, staff, "staff.audit_log_view", org_id=org_id,
                          org_name=org.name, details=f"строк: {len(entries)}")
    return page


def _user_out(db: Session, user: User) -> StaffUserOut:
    orgs = []
    for org, role in crud.list_user_organizations(db, user.id):
        membership = crud.get_membership(db, org.id, user.id)
        orgs.append(StaffUserOrgOut(
            id=org.id, name=org.name, role=role,
            blocked=membership is not None and membership.blocked_at is not None,
            block_reason=membership.block_reason if membership else "",
            last_seen_at=membership.last_seen_at if membership else None))
    return StaffUserOut(id=user.id, email=user.email, full_name=user.full_name,
                        created_at=user.created_at, is_staff=user.is_staff,
                        has_password=user.hashed_password is not None, organizations=orgs)


@router.get("/users", response_model=list[StaffUserOut])
def search_users(q: str = "", limit: int = 50, staff: User = Depends(require_staff),
                 db: Session = Depends(get_db)) -> list[StaffUserOut]:
    """Поиск человека по адресу или имени — вход в разбор обращения в поддержку.

    Ответ говорит и то, о чём поддержку спрашивают чаще всего: заведён ли пароль вообще
    (приглашённый его мог не задать) и не приостановлен ли доступ — и в какой именно
    организации. Это метаданные человека, а не данные организации, поэтому запись идёт
    в служебный журнал.
    """
    limit = max(1, min(limit, 200))
    users = crud.search_users(db, q=q, limit=limit)
    crud.log_staff_action(db, staff, "staff.users_search",
                          details=f"найдено: {len(users)}" + (f", отбор: {q}" if q else ""))
    return [_user_out(db, u) for u in users]


@router.get("/users/{user_id}", response_model=StaffUserOut)
def get_user(user_id: str, staff: User = Depends(require_staff),
             db: Session = Depends(get_db)) -> StaffUserOut:
    user = crud.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    crud.log_staff_action(db, staff, "staff.user_view", details=user.email)
    return _user_out(db, user)


@router.get("/log", response_model=StaffLogPage)
def read_staff_log(limit: int = 200, actor: str = "", org_id: str = "",
                   staff: User = Depends(require_staff),
                   db: Session = Depends(get_db)) -> StaffLogPage:
    """Служебный журнал: где были наши сотрудники.

    Как и журнал организации — только чтение: ни PUT, ни DELETE. Журнал, который можно
    поправить, не журнал, и для собственных следов это верно ровно в той же мере.
    Собственное чтение журнала не пишется: оно никуда не приходит и ничего не выносит.
    """
    limit = max(1, min(limit, 500))
    entries = crud.list_staff_log(db, limit=limit, actor=actor, org_id=org_id)
    return StaffLogPage(entries=[
        StaffLogEntryOut(id=e.id, actor_email=e.actor_email, action=e.action,
                         organization_id=e.organization_id,
                         organization_name=e.organization_name, details=e.details,
                         created_at=e.created_at) for e in entries])
