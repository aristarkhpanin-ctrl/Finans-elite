"""REST-эндпоинты организаций и членства (6.2 + аутентификация 6.3 + RBAC 6.4)."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from .. import billing, crud, mail
from ..access import restriction_for
from ..database import get_db
from ..db_models import User
from ..deps import current_user, require_membership, require_org_permission
from ..mail import Sent, access_link_letter, invite_letter, mail_enabled
from ..plans import PRODUCTS
from ..rbac import Perm, is_valid_role
from ..schemas import (
    AccessLinkOut,
    AuditLogEntryOut,
    AuditLogPage,
    BenchmarkIn,
    BenchmarkOut,
    MailReport,
    MemberBlockIn,
    MemberCreate,
    MemberOut,
    MemberPatch,
    OrganizationCreate,
    OrganizationMembershipOut,
    OrganizationOut,
    RestrictionOut,
    TransferOwnershipIn,
)
from ..security import create_invite_token, create_reset_token


def _benchmark_out(b) -> BenchmarkOut:
    return BenchmarkOut(id=b.id, industry=b.industry, metric=b.metric,
                        value=Decimal(b.value), source=b.source, updated_at=b.updated_at)


#: Предел строк в выгрузке. Не «весь журнал»: файл на миллион строк не откроется там,
#: где его собираются читать, а молчаливая обрезка хуже названного предела.
MAX_LOG_EXPORT = 10_000

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(body: OrganizationCreate, user: User = Depends(current_user),
                        db: Session = Depends(get_db)) -> OrganizationOut:
    """Создать организацию; создатель становится её владельцем."""
    org = crud.create_organization(db, body.name)
    crud.add_membership(db, org.id, user.id, role="owner")
    crud.log_action(db, org.id, user, "org.create", entity_type="organization",
                    entity_id=org.id, entity_name=org.name)
    return OrganizationOut(id=org.id, name=org.name, created_at=org.created_at)


def _restrictions_out(db: Session, org_id: str) -> list[RestrictionOut]:
    """Режим доступа организации по каждому продукту (B2).

    Считается **тем же** :func:`access.restriction_for`, что и отказывает на записи:
    второй источник этой правды однажды разошёлся бы с первым, и клиент видел бы
    спокойный экран, на котором ничего не сохраняется.
    """
    out = []
    for product in PRODUCTS:
        restriction = restriction_for(db, org_id, product)
        if restriction is not None:
            out.append(RestrictionOut(product=product, kind=restriction.kind,
                                      reason=restriction.reason, remedy=restriction.remedy))
    return out


@router.get("", response_model=list[OrganizationMembershipOut])
def my_organizations(user: User = Depends(current_user),
                     db: Session = Depends(get_db)) -> list[OrganizationMembershipOut]:
    """Организации текущего пользователя (с его ролью и режимом доступа в каждой)."""
    return [
        OrganizationMembershipOut(id=org.id, name=org.name, role=role,
                                  created_at=org.created_at,
                                  restrictions=_restrictions_out(db, org.id))
        for org, role in crud.list_user_organizations(db, user.id)
    ]


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(org_id: str = Depends(require_membership),
                     db: Session = Depends(get_db)) -> OrganizationOut:
    org = crud.get_organization(db, org_id)
    return OrganizationOut(id=org.id, name=org.name, created_at=org.created_at)


def _log_entry_out(e) -> AuditLogEntryOut:
    return AuditLogEntryOut(id=e.id, actor_email=e.actor_email, action=e.action,
                            entity_type=e.entity_type, entity_id=e.entity_id,
                            entity_name=e.entity_name, details=e.details,
                            created_at=e.created_at)


def _mail_report(sent: Sent) -> MailReport:
    """Исход отправки — в ответ, а не только в лог: письмо, потерянное молча, хуже
    неотправленного (D1)."""
    return MailReport(attempted=sent.attempted, ok=sent.ok, error=sent.error)


def _member_out(membership, user, *, invite_token: str | None = None,
                mail: MailReport | None = None) -> MemberOut:
    """Ответ об участнике — из одного места: состояние блокировки нельзя забыть."""
    return MemberOut(
        user_id=user.id, email=user.email, full_name=user.full_name,
        role=membership.role, blocked=membership.blocked_at is not None,
        blocked_at=membership.blocked_at, blocked_by=membership.blocked_by,
        block_reason=membership.block_reason, last_seen_at=membership.last_seen_at,
        mail=mail,
        **({"invite_token": invite_token} if invite_token is not None else {}),
    )


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
    # Приглашённому, у которого ещё нет пароля, нужен способ его завести. Ссылка
    # активации возвращается пригласившему **всегда**: письмо (D1) — добавление к
    # «передайте лично», а не замена, и при неудачной отправке передавать её всё равно
    # придётся ему. В списке участников токена нет: там он был бы вечным пропуском в
    # чужой аккаунт для всякого, кто видит состав организации.
    invite = None if user.hashed_password else create_invite_token(user.id)
    report = MailReport()
    if invite is not None and mail_enabled():
        org = crud.get_organization(db, org_id)
        report = _mail_report(mail.send(user.email, invite_letter(
            organization=org.name if org else "", inviter=actor.email, token=invite)))
        crud.log_action(db, org_id, actor, "member.invite_mail", entity_type="member",
                        entity_id=user.id, entity_name=user.email,
                        details="письмо отправлено" if report.ok
                                else f"письмо не ушло: {report.error}")
    return _member_out(membership, user, invite_token=invite, mail=report)


@router.get("/{org_id}/members", response_model=list[MemberOut])
def list_members(org_id: str = Depends(require_org_permission(Perm.MEMBER_READ)),
                 db: Session = Depends(get_db)) -> list[MemberOut]:
    return [_member_out(m, u) for m, u in crud.list_members(db, org_id)]


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
    return _member_out(updated, user)


@router.post("/{org_id}/transfer-ownership", response_model=list[MemberOut])
def transfer_ownership(body: TransferOwnershipIn,
                       org_id: str = Depends(require_org_permission(Perm.ORG_MANAGE)),
                       actor: User = Depends(current_user),
                       db: Session = Depends(get_db)) -> list[MemberOut]:
    """Передать владение организацией другому участнику (C3).

    Появилось вместе с правом удалить учётную запись: без передачи владелец не мог им
    воспользоваться — организация без владельца это компания без того, кто платит за
    тариф и управляет доступом. Понизить владельца по отдельности по-прежнему нельзя
    (иначе организация осталась бы вовсе без него); здесь это **одно действие**, в
    котором новый владелец появляется раньше, чем прежний перестаёт им быть.

    Прежний владелец становится администратором, а не выбывает: человек, отдавший
    компанию, чаще всего продолжает в ней работать, и выкидывать его молча незачем.
    """
    if body.user_id == actor.id:
        raise HTTPException(status_code=400, detail="Вы уже владелец организации")
    target = _member_or_404(db, org_id, body.user_id)
    mine = _member_or_404(db, org_id, actor.id)
    if mine.role != "owner":
        raise HTTPException(status_code=403, detail="Передать владение может только владелец")
    if target.blocked_at is not None:
        raise HTTPException(
            status_code=409,
            detail="У этого участника приостановлен доступ: сначала верните ему доступ")

    crud.set_membership_role(db, target, "owner")
    crud.set_membership_role(db, mine, "admin")
    new_owner = crud.get_user(db, body.user_id)
    crud.log_action(db, org_id, actor, "org.transfer_ownership", entity_type="member",
                    entity_id=new_owner.id, entity_name=new_owner.email,
                    details=f"владение передано: {actor.email} → {new_owner.email}")
    return [_member_out(target, new_owner), _member_out(mine, actor)]


@router.post("/{org_id}/members/{user_id}/block", response_model=MemberOut)
def block_member(user_id: str, body: MemberBlockIn,
                 org_id: str = Depends(require_org_permission(Perm.MEMBER_MANAGE)),
                 actor: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> MemberOut:
    """Приостановить доступ участника в этой организации (право member.manage).

    **Приостановка — не удаление.** Участник остаётся в списке со своей ролью и историей;
    доступ возвращается одним действием. Удаление стирает связь, и восстановить его можно
    только заведением заново — с потерей того, кем человек был.

    Отзыв **мгновенный**: членство читается из базы на каждом запросе, поэтому выданный
    ранее токен доступа не даёт (см. `deps._ensure_active`). Блокируется членство, а не
    учётная запись: в других организациях человек продолжает работать — там свои
    администраторы, и распоряжаться чужим доступом эти не вправе.
    """
    membership = _member_or_404(db, org_id, user_id)
    if membership.role == "owner":
        # Иначе администратор отстраняет владельца и забирает организацию с тарифом и
        # биллингом — тот же запрет, что у удаления и у ссылки сброса пароля.
        raise HTTPException(status_code=409,
                            detail="Нельзя приостановить доступ владельца организации")
    if user_id == actor.id:
        raise HTTPException(status_code=409, detail="Нельзя приостановить себя")
    if membership.blocked_at is not None:
        raise HTTPException(status_code=409, detail="Доступ участника уже приостановлен")

    user = crud.get_user(db, user_id)
    updated = crud.set_membership_block(db, membership, blocked=True,
                                        by=actor.email, reason=body.reason.strip())
    crud.log_action(db, org_id, actor, "member.block", entity_type="member",
                    entity_id=user_id, entity_name=user.email if user else user_id,
                    details=body.reason.strip())
    return _member_out(updated, user)


@router.delete("/{org_id}/members/{user_id}/block", response_model=MemberOut)
def unblock_member(user_id: str,
                   org_id: str = Depends(require_org_permission(Perm.MEMBER_MANAGE)),
                   actor: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> MemberOut:
    """Вернуть доступ участнику. Причина прошлой блокировки стирается, след в журнале —
    остаётся: журнал и есть то, что помнит."""
    membership = _member_or_404(db, org_id, user_id)
    if membership.blocked_at is None:
        raise HTTPException(status_code=409, detail="Доступ участника не приостановлен")
    was = membership.block_reason
    user = crud.get_user(db, user_id)
    updated = crud.set_membership_block(db, membership, blocked=False)
    crud.log_action(db, org_id, actor, "member.unblock", entity_type="member",
                    entity_id=user_id, entity_name=user.email if user else user_id,
                    details=f"была причина: {was}" if was else "")
    return _member_out(updated, user)


@router.post("/{org_id}/members/{user_id}/access-link", response_model=AccessLinkOut)
def issue_access_link(user_id: str,
                      org_id: str = Depends(require_org_permission(Perm.MEMBER_MANAGE)),
                      actor: User = Depends(current_user),
                      db: Session = Depends(get_db)) -> AccessLinkOut:
    """Выдать участнику одноразовую ссылку входа: приглашение или сброс пароля.

    Закрывает дыру доступности: до этого забытый пароль было не сбросить **никому** —
    ни пользователю, ни администратору, — и учётная запись терялась насовсем. Ссылка
    передаётся лично: почтовой отправки у платформы нет.

    Два запрета, без которых это была бы не функция, а эскалация прав:

    * **Владельцу ссылка не выдаётся.** Иначе администратор сбрасывает пароль владельцу
      и забирает организацию вместе с тарифом и биллингом. Владелец — единственная роль
      без пути восстановления, и это осознанный размен: захват организации хуже.
    * **Участнику, состоящему и в других организациях, — тоже.** Пароль один на
      платформу, и администратор одной организации, сбросив его, получил бы доступ во
      все остальные. Здесь администратор распоряжается не своим.

    Обе причины называются в ответе, а не превращаются в молчаливый отказ.
    """
    membership = _member_or_404(db, org_id, user_id)
    user = crud.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    if membership.role == "owner":
        raise HTTPException(
            status_code=409,
            detail="Владельцу организации ссылка входа не выдаётся: иначе администратор "
                   "мог бы сбросить его пароль и забрать организацию.")
    if len(crud.list_user_memberships(db, user_id)) > 1:
        raise HTTPException(
            status_code=409,
            detail="Участник состоит и в других организациях. Пароль один на платформу, "
                   "и сброс отсюда открыл бы доступ к ним — ссылку может выдать только "
                   "администратор той организации, где участник состоит один.")

    # Пароля нет — участник ещё не активировал приглашение, и нужна именно новая
    # ссылка приглашения (прежняя могла потеряться или истечь).
    kind = "reset" if user.hashed_password else "invite"
    token = (create_reset_token(user.id, user.hashed_password) if kind == "reset"
             else create_invite_token(user.id))
    # Выдача ссылки — событие для журнала наравне с добавлением участника: ею
    # получают доступ к учётной записи.
    crud.log_action(db, org_id, actor, "member.access_link", entity_type="member",
                    entity_id=user.id, entity_name=user.email,
                    details="сброс пароля" if kind == "reset" else "повторное приглашение")
    report = MailReport()
    if mail_enabled():
        org = crud.get_organization(db, org_id)
        report = _mail_report(mail.send(user.email, access_link_letter(
            kind=kind, organization=org.name if org else "", issued_by=actor.email,
            token=token)))
    # Ссылка возвращается **в любом случае** — и при неудачной отправке, и при
    # успешной: письмо может не дойти молча (спам-фильтр, опечатка в адресе), и
    # администратору нужно, чем его заменить.
    return AccessLinkOut(user_id=user.id, email=user.email, kind=kind, token=token,
                         mail=report)


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


@router.get("/{org_id}/benchmarks", response_model=list[BenchmarkOut])
def list_benchmarks(org_id: str = Depends(require_membership),
                    db: Session = Depends(get_db)) -> list[BenchmarkOut]:
    """Отраслевые ориентиры организации — её собственные числа, а не рынок."""
    return [_benchmark_out(b) for b in crud.list_benchmarks(db, org_id)]


@router.put("/{org_id}/benchmarks", response_model=list[BenchmarkOut])
def replace_benchmarks(body: list[BenchmarkIn],
                       org_id: str = Depends(require_org_permission(Perm.ORG_MANAGE)),
                       actor: User = Depends(current_user),
                       db: Session = Depends(get_db)) -> list[BenchmarkOut]:
    """Заменить справочник целиком (правится как таблица — сохраняется как таблица).

    Право `org.manage`: ориентиры — общая память организации, по которой оценивают
    сделки; правит их тот же, кто отвечает за организацию.
    """
    pairs = {(" ".join(b.industry.split()).casefold(), b.metric) for b in body}
    if len(pairs) != len(body):
        raise HTTPException(
            status_code=422,
            detail="Два ориентира на одну пару «отрасль + метрика»: платформа не может "
                   "выбрать между ними за вас.")
    rows = [{"industry": b.industry.strip(), "metric": b.metric, "value": str(b.value),
             "source": b.source.strip()} for b in body]
    saved = crud.replace_benchmarks(db, org_id, rows)
    crud.log_action(db, org_id, actor, "benchmarks.replace", entity_type="organization",
                    entity_id=org_id, details=f"строк: {len(rows)}")
    return [_benchmark_out(b) for b in saved]


@router.get("/{org_id}/audit-log", response_model=AuditLogPage)
def read_audit_log(limit: int = 200, before: datetime | None = None,
                   actor: str = "", action: str = "", entity_type: str = "",
                   since: datetime | None = None, until: datetime | None = None,
                   q: str = "",
                   org_id: str = Depends(require_org_permission(Perm.ORG_MANAGE)),
                   db: Session = Depends(get_db)) -> AuditLogPage:
    """Журнал действий организации (право org.manage): новые записи сверху.

    Отбор — по участнику, действию, виду сущности, диапазону дат и подстроке (имя
    сущности, почта актора, примечание). Без отбора журнал на десятки тысяч записей
    существует, но ответа из него не достать: пролистать двадцать тысяч строк никто не
    станет. ``total`` считается **под теми же условиями**, иначе «50 из 12 000» врало бы.

    Только чтение. Ни PUT, ни DELETE у журнала нет и не будет: журнал, который можно
    поправить, не журнал. Срок хранения (5 лет, ARCHITECTURE §4) — политика эксплуатации,
    а не логика приложения: чистка кодом означала бы, что приложение умеет стирать
    собственные следы.
    """
    limit = max(1, min(limit, 500))
    f = {"actor": actor, "action": action, "entity_type": entity_type,
         "since": since, "until": until, "q": q}
    entries = crud.list_audit_log(db, org_id, limit=limit, before=before, **f)
    return AuditLogPage(
        entries=[_log_entry_out(e) for e in entries],
        total=crud.count_audit_log(db, org_id, **f),
        actors=crud.audit_log_actors(db, org_id),
        actions=crud.audit_log_actions(db, org_id),
    )


@router.get("/{org_id}/audit-log.csv")
def export_audit_log(actor: str = "", action: str = "", entity_type: str = "",
                     since: datetime | None = None, until: datetime | None = None,
                     q: str = "",
                     org_id: str = Depends(require_org_permission(Perm.ORG_MANAGE)),
                     actor_user: User = Depends(current_user),
                     db: Session = Depends(get_db)) -> Response:
    """Выгрузка журнала в CSV — под теми же условиями отбора, что и на экране.

    **Сама выгрузка пишется в журнал**: вынос следов наружу — тоже событие, и оно
    единственное, о котором журнал иначе умолчал бы.

    Разделитель — точка с запятой, кодировка с BOM: иначе Excel в русской локали
    раскладывает файл в один столбец и портит кириллицу, и выгрузка становится
    бесполезной ровно для тех, кому она нужна.
    """
    f = {"actor": actor, "action": action, "entity_type": entity_type,
         "since": since, "until": until, "q": q}
    entries = crud.list_audit_log(db, org_id, limit=MAX_LOG_EXPORT, **f)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Дата и время", "Кто", "Действие", "Тип", "Объект", "Примечание"])
    for e in entries:
        writer.writerow([e.created_at.strftime("%d.%m.%Y %H:%M:%S"), e.actor_email,
                         e.action, e.entity_type, e.entity_name, e.details])
    crud.log_action(db, org_id, actor_user, "audit_log.export", entity_type="organization",
                    entity_id=org_id, details=f"строк: {len(entries)}")
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )
