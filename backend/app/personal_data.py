"""Свои данные: выгрузка и удаление учётной записи (152-ФЗ) — C3.

Два права человека, которых у платформы не было вовсе: забрать то, что о нём хранится, и
уйти. Оба сделаны так, чтобы **не обещать больше, чем происходит на самом деле**.

**Выгрузка персональных данных — не выгрузка данных организации.** Проекты и дела
принадлежат компании, а не сотруднику: отдать их «по запросу субъекта персональных
данных» значило бы выдать уходящему сотруднику модели работодателя под видом личного
права. Выгрузка компании существует отдельно (документы и таблицы на своих экранах) и
доступна тому, у кого есть права в организации.

**Что удаление стирает и чего не стирает — сказано до нажатия.** Записи журнала остаются:
они принадлежат организациям, где человек работал, и отвечают на вопрос «кто это сделал»
— ровно ради этого журнал и ведётся. Молча оставить их, пообещав «полное удаление», было
бы неправдой; молча стереть — сломать чужой журнал.

**Секрет второго фактора в выгрузку не попадает.** Это не «данные о человеке», а ключ от
его учётной записи: файл, который кладут в почту и в облако, не место для ключа.

**Журнал и содержимое организаций читаются через дверь арендатора** (:func:`as_tenant`),
организация за организацией — как их читают её участники и как их обходит служебный
контур. Запрос «все мои записи разом» вернул бы на PostgreSQL пустоту (RLS), а на SQLite
работал бы: расхождение, которое обнаружилось бы на живых данных.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crud
from .database import as_tenant
from .db_models import (
    AnalysisJob,
    AuditGroup,
    AuditLogEntry,
    AuditSubject,
    AuditSubjectVersion,
    Holding,
    HoldingMember,
    IndustryBenchmark,
    Membership,
    Organization,
    Payment,
    Project,
    ProjectVersion,
    Subscription,
    User,
)

#: Сколько записей журнала кладём в выгрузку. Предел назван, и выгрузка **говорит о
#: своей неполноте**: молча обрезанный файл выглядит как полный.
MAX_EXPORT_LOG = 5_000


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.isoformat()


def build_export(db: Session, user: User) -> dict:
    """Всё, что платформа хранит **о человеке** — одним файлом.

    Первым блоком идёт объяснение, что внутри и чего внутри нет: файл уедет к человеку
    без нас, и приложить оговорку к нему больше будет негде.
    """
    memberships = crud.list_user_memberships(db, user.id)
    orgs = {o.id: o for o in db.execute(select(Organization).where(
        Organization.id.in_([m.organization_id for m in memberships]))).scalars()} \
        if memberships else {}

    actions: list[dict] = []
    total_entries = 0
    for membership in memberships:
        org_id = membership.organization_id
        name = orgs[org_id].name if org_id in orgs else ""
        with as_tenant(db, org_id):
            total_entries += crud.count_user_log_entries(db, org_id, user.id)
            actions.extend(
                {
                    "когда": _iso(e.created_at),
                    "организация": name,
                    "действие": e.action,
                    "над_чем": e.entity_name or e.entity_type,
                    "примечание": e.details,
                }
                for e in crud.list_user_log_entries(db, org_id, user.id, MAX_EXPORT_LOG)
            )
    actions.sort(key=lambda a: a["когда"] or "", reverse=True)
    del actions[MAX_EXPORT_LOG:]

    about = [
        "Здесь персональные данные, которые платформа хранит о вас: учётная запись, "
        "участие в организациях, входы и ваши действия из журнала.",
        "Проектов и дел здесь нет: они принадлежат организациям, а не вам лично. "
        "Выгрузить их можно на экранах самих проектов и дел, если у вас есть права.",
        "Секрета второго фактора здесь нет: это ключ от вашей учётной записи, а не "
        "сведения о вас. Файл, который кладут в почту, — не место для ключа.",
        "Действия показаны по организациям, где вы состоите сейчас. Записи в тех, "
        "которые вы покинули, остались у них: журнал принадлежит организации.",
    ]
    if total_entries > len(actions):
        about.append(f"Записей журнала у вас {total_entries}, в файл вошли последние "
                     f"{len(actions)}: остальные видны в журнале организации.")

    return {
        "о_выгрузке": {
            "составлена": _iso(datetime.now(timezone.utc)),
            "что_внутри": about,
        },
        "учётная_запись": {
            "адрес": user.email,
            "имя": user.full_name,
            "зарегистрирован": _iso(user.created_at),
            "пароль_задан": user.hashed_password is not None,
            "второй_фактор": "включён" if user.totp_enabled_at else "не включён",
            "сотрудник_платформы": bool(user.is_staff),
            "доступ_заблокирован": _iso(user.blocked_at),
            "причина_блокировки": user.block_reason or None,
        },
        "организации": [
            {
                "название": orgs[m.organization_id].name if m.organization_id in orgs else "",
                "роль": m.role,
                "участник_с": _iso(m.created_at),
                "последнее_обращение": _iso(m.last_seen_at),
                "доступ_приостановлен": _iso(m.blocked_at),
                "причина": m.block_reason or None,
            }
            for m in memberships
        ],
        "входы": [
            {
                "устройство": s.user_agent,
                "адрес": s.ip,
                "начат": _iso(s.created_at),
                "последнее_обращение": _iso(s.last_seen_at),
                "действует_до": _iso(s.expires_at),
                "закрыт": _iso(s.revoked_at),
            }
            for s in crud.list_all_sessions(db, user.id)
        ],
        "мои_действия": actions,
    }


@dataclass
class DeletionPlan:
    """Что произойдёт при удалении учётной записи — **до** нажатия кнопки.

    Удаление необратимо, а его последствия выходят за пределы одного человека: вместе с
    ним может исчезнуть организация со всеми моделями. Показать это списком — не
    вежливость, а единственный способ дать согласие осознанно.
    """

    #: Организации, которые исчезнут вместе с учётной записью (человек в них один).
    organizations_deleted: list[str] = field(default_factory=list)
    #: Организации, из которых человек просто выйдет.
    organizations_left: list[str] = field(default_factory=list)
    #: Что удалить нельзя, пока не сделано названное действие.
    blockers: list[str] = field(default_factory=list)
    #: Что останется после удаления — и почему.
    kept: list[str] = field(default_factory=list)
    projects: int = 0
    cases: int = 0

    @property
    def allowed(self) -> bool:
        return not self.blockers


def deletion_plan(db: Session, user: User) -> DeletionPlan:
    """Собрать план удаления: что исчезнет, что останется, что мешает.

    **Владелец организации, где есть другие люди, удалиться не может.** Не из вредности:
    организация без владельца — это компания без того, кто платит за тариф и управляет
    доступом; молча оставить её такой значило бы сломать работу остальных. Выход назван —
    передать владение.
    """
    plan = DeletionPlan()
    for membership in crud.list_user_memberships(db, user.id):
        org = crud.get_organization(db, membership.organization_id)
        name = org.name if org else membership.organization_id
        members = crud.count_members(db, membership.organization_id)
        if membership.role == "owner" and members > 1:
            plan.blockers.append(
                f"Вы владелец организации «{name}», в ней ещё {members - 1} чел. "
                "Передайте владение другому участнику — или удалите их из организации.")
            continue
        if membership.role == "owner":
            plan.organizations_deleted.append(name)
            with as_tenant(db, membership.organization_id):
                plan.projects += crud.count_projects(db, membership.organization_id)
                plan.cases += crud.count_audit_subjects(db, membership.organization_id)
        else:
            plan.organizations_left.append(name)

    plan.kept = [
        "Записи журнала в организациях, где вы работали: они принадлежат этим "
        "организациям и отвечают на вопрос «кто это сделал». Ваш адрес в них останется.",
    ]
    if plan.organizations_deleted:
        plan.kept.append(
            "Платёжные записи удаляемых организаций стираются вместе с ними; "
            "бухгалтерские документы у платёжного провайдера этим не затрагиваются.")
    return plan


def delete_account(db: Session, user: User) -> DeletionPlan:
    """Удалить учётную запись по плану. Вызывающий обязан проверить :attr:`allowed`.

    Удаление идёт **явными запросами**, а не каскадом базы: на SQLite внешние ключи по
    умолчанию не действуют, и каскад, работающий в продакшене, молча не сработал бы в
    тестах — расхождение, которое обнаружилось бы на живых данных.
    """
    plan = deletion_plan(db, user)
    if not plan.allowed:
        raise ValueError("удаление невозможно: есть препятствия")

    for membership in list(crud.list_user_memberships(db, user.id)):
        org_id = membership.organization_id
        if membership.role == "owner":
            _purge_organization(db, org_id)
        else:
            db.delete(membership)
    db.commit()
    _purge_user(db, user)
    return plan


def _purge_organization(db: Session, org_id: str) -> None:
    """Стереть организацию и всё, что ей принадлежит.

    Порядок — от зависимых к главным, чтобы не осталось строк, ссылающихся в пустоту.
    Журнал этой организации уходит вместе с ней: он её собственность, а не платформы, и
    хранить его после того, как хранить его больше некому, незачем.

    Всё — **внутри арендатора**: половина этих таблиц под RLS, и запрос без него стёр бы
    на PostgreSQL ноль строк, оставив организацию с данными, которых никто уже не видит.
    """
    with as_tenant(db, org_id):
        holdings = [h.id for h in db.execute(
            select(Holding.id).where(Holding.organization_id == org_id)).scalars()]
        for holding_id in holdings:
            for member in db.execute(select(HoldingMember).where(
                    HoldingMember.holding_id == holding_id)).scalars():
                db.delete(member)
        for model in (ProjectVersion, AuditSubjectVersion, AnalysisJob, Project,
                      AuditSubject, AuditGroup, Holding, IndustryBenchmark, Subscription,
                      Payment, AuditLogEntry, Membership):
            for row in db.execute(select(model).where(
                    model.organization_id == org_id)).scalars():
                db.delete(row)
        db.flush()
    org = db.get(Organization, org_id)
    if org is not None:
        db.delete(org)
    db.commit()


def _purge_user(db: Session, user: User) -> None:
    """Обезличить учётную запись и стереть входы.

    Строка пользователя **остаётся**, но пустой: на неё ссылается журнал (``user_id``), и
    удалить её значило бы либо порвать эти ссылки, либо утащить за собой чужие записи.
    Адрес заменяется меткой удаления — войти по нему больше нельзя, а «надгробие» в
    журнале (`actor_email`) остаётся тем, чем было: журнал обязан отвечать «кто это
    сделал» и после ухода человека.
    """
    for session in crud.list_all_sessions(db, user.id):
        db.delete(session)
    user.email = f"удалён-{user.id}@удалён"
    user.full_name = ""
    user.hashed_password = None
    user.totp_secret = ""
    user.totp_enabled_at = None
    user.totp_recovery = []
    user.blocked_at = datetime.now(timezone.utc)
    user.block_reason = "Учётная запись удалена по запросу владельца"
    user.blocked_by = "самостоятельное удаление"
    db.commit()
