"""CRUD-операции: организации, пользователи, членство, проекты.

Проекты изолированы по ``organization_id`` (мультиарендность, 6.2).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from audit_core import AuditSubjectModel
from calc_core import ProjectModel

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
    StaffLogEntry,
    Subscription,
    User,
)
from .plans import DEFAULT_PLAN
from .schemas import AuditGroupModel

# --- Фоновые задачи анализа (Celery) ---

def create_analysis_job(db: Session, job_id: str, org_id: str, project_id: str, kind: str) -> AnalysisJob:
    job = AnalysisJob(id=job_id, organization_id=org_id, project_id=project_id, kind=kind)
    db.add(job)
    db.commit()
    return job


def get_analysis_job(db: Session, job_id: str) -> AnalysisJob | None:
    return db.get(AnalysisJob, job_id)

# --- Организации ---

def create_organization(db: Session, name: str, plan_code: str = DEFAULT_PLAN) -> Organization:
    org = Organization(name=name)
    db.add(org)
    db.flush()  # получить org.id до создания подписки
    db.add(Subscription(organization_id=org.id, plan_code=plan_code))
    db.commit()
    db.refresh(org)
    return org


def get_organization(db: Session, org_id: str) -> Organization | None:
    return db.get(Organization, org_id)


# --- Подписки ---

def get_subscription(db: Session, org_id: str, product: str = "business") -> Subscription | None:
    """Подписка организации на продукт (у каждого продукта своя)."""
    return db.scalar(select(Subscription).where(
        Subscription.organization_id == org_id, Subscription.product == product))


def list_subscriptions(db: Session, org_id: str) -> list[Subscription]:
    return list(db.scalars(select(Subscription).where(
        Subscription.organization_id == org_id).order_by(Subscription.product)))


def set_plan(db: Session, org_id: str, plan_code: str, status: str = "active",
             product: str = "business") -> Subscription:
    sub = get_subscription(db, org_id, product)
    if sub is None:
        sub = Subscription(organization_id=org_id, plan_code=plan_code, status=status,
                           product=product)
        db.add(sub)
    else:
        sub.plan_code = plan_code
        sub.status = status
    db.commit()
    db.refresh(sub)
    return sub


# --- Платежи ---

def create_payment(db: Session, org_id: str, plan_code: str, amount_rub: int,
                   provider: str = "yookassa") -> Payment:
    payment = Payment(organization_id=org_id, plan_code=plan_code, amount_rub=amount_rub,
                      provider=provider, status="pending")
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def get_payment(db: Session, payment_id: str) -> Payment | None:
    return db.get(Payment, payment_id)


def get_payment_by_provider_id(db: Session, provider_payment_id: str) -> Payment | None:
    return db.scalar(
        select(Payment).where(Payment.provider_payment_id == provider_payment_id)
    )


def set_payment_provider_id(db: Session, payment: Payment, provider_payment_id: str) -> Payment:
    payment.provider_payment_id = provider_payment_id
    db.commit()
    db.refresh(payment)
    return payment


def mark_payment(db: Session, payment: Payment, status: str) -> Payment:
    payment.status = status
    db.commit()
    db.refresh(payment)
    return payment


def count_projects(db: Session, org_id: str) -> int:
    return db.scalar(
        select(func.count()).select_from(Project).where(Project.organization_id == org_id)
    ) or 0


def count_audit_subjects(db: Session, org_id: str) -> int:
    """Число дел организации — единица квоты продукта «Финанс-Аудит»."""
    return db.scalar(
        select(func.count()).select_from(AuditSubject)
        .where(AuditSubject.organization_id == org_id)
    ) or 0


def count_members(db: Session, org_id: str) -> int:
    return db.scalar(
        select(func.count()).select_from(Membership).where(Membership.organization_id == org_id)
    ) or 0


# --- Пользователи и членство ---

def get_user(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def create_user(db: Session, email: str, full_name: str = "",
                hashed_password: str | None = None) -> User:
    user = User(email=email, full_name=full_name, hashed_password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_user(db: Session, email: str, full_name: str = "") -> User:
    user = get_user_by_email(db, email)
    if user is None:
        user = create_user(db, email, full_name)
    return user


def set_password(db: Session, user: User, hashed: str) -> User:
    user.hashed_password = hashed
    db.commit()
    db.refresh(user)
    return user


def set_full_name(db: Session, user: User, full_name: str) -> User:
    user.full_name = full_name
    db.commit()
    db.refresh(user)
    return user


def add_membership(db: Session, org_id: str, user_id: str, role: str = "owner") -> Membership:
    existing = db.scalar(
        select(Membership).where(
            Membership.organization_id == org_id, Membership.user_id == user_id
        )
    )
    if existing is not None:
        return existing
    membership = Membership(organization_id=org_id, user_id=user_id, role=role)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def add_member(db: Session, org_id: str, email: str, full_name: str = "",
               role: str = "owner") -> Membership:
    user = get_or_create_user(db, email, full_name)
    return add_membership(db, org_id, user.id, role)


def list_user_memberships(db: Session, user_id: str) -> list[Membership]:
    return list(
        db.scalars(
            select(Membership)
            .where(Membership.user_id == user_id)
            .order_by(Membership.created_at)
        )
    )


def get_membership(db: Session, org_id: str, user_id: str) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.organization_id == org_id, Membership.user_id == user_id
        )
    )


def is_member(db: Session, org_id: str, user_id: str) -> bool:
    return get_membership(db, org_id, user_id) is not None


def get_role(db: Session, org_id: str, user_id: str) -> str | None:
    membership = get_membership(db, org_id, user_id)
    return membership.role if membership else None


def set_membership_role(db: Session, membership: Membership, role: str) -> Membership:
    membership.role = role
    db.commit()
    db.refresh(membership)
    return membership


def remove_membership(db: Session, membership: Membership) -> None:
    db.delete(membership)
    db.commit()


def set_membership_block(db: Session, membership: Membership, *, blocked: bool,
                         by: str = "", reason: str = "") -> Membership:
    """Приостановить или вернуть доступ участника (A1).

    Снятие **стирает** автора и причину: оставленная причина от прошлой блокировки
    рассказывала бы о действующем участнике то, чего уже нет.
    """
    membership.blocked_at = datetime.now(timezone.utc) if blocked else None
    membership.blocked_by = by[:255] if blocked else ""
    membership.block_reason = reason[:500] if blocked else ""
    db.commit()
    db.refresh(membership)
    return membership


def list_user_organizations(db: Session, user_id: str) -> list[tuple[Organization, str]]:
    rows = db.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user_id)
        .order_by(Membership.created_at)
    ).all()
    return [(org, role) for org, role in rows]


def list_members(db: Session, org_id: str) -> list[tuple[Membership, User]]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == org_id)
        .order_by(Membership.created_at)
    ).all()
    return [(m, u) for m, u in rows]


# --- Проекты (в пределах организации) ---

def create_project(db: Session, org_id: str, name: str, model: ProjectModel) -> Project:
    project = Project(organization_id=org_id, name=name, model=model.model_dump(mode="json"))
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session, org_id: str) -> list[Project]:
    return list(
        db.scalars(
            select(Project)
            .where(Project.organization_id == org_id)
            .order_by(Project.created_at.desc())
        )
    )


def get_project(db: Session, org_id: str, project_id: str) -> Project | None:
    return db.scalar(
        select(Project).where(
            Project.id == project_id, Project.organization_id == org_id
        )
    )


def model_hash(model: dict) -> str:
    """SHA-256 канонического JSON модели (сорт. ключи) — стабильный отпечаток для дрейфа."""
    canonical = json.dumps(model, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def update_project(db: Session, project: Project, *, name: str | None = None,
                   model: ProjectModel | None = None) -> Project:
    if name is not None:
        project.name = name
    if model is not None:
        project.model = model.model_dump(mode="json")
        # Изменение модели снимает финализацию: подтверждён был другой план (гейт ревью).
        project.status = "draft"
    db.commit()
    db.refresh(project)
    return project


def finalize_project(db: Session, project: Project, review: dict) -> Project:
    """Отметить проект финализированным: снимок ревью + отпечаток модели (Ф10)."""
    project.status = "finalized"
    project.finalized_at = datetime.now(timezone.utc)
    project.finalized_model_hash = model_hash(project.model)
    project.finalized_review = review
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: Project) -> None:
    db.delete(project)
    db.commit()


def load_model(project: Project) -> ProjectModel:
    """Десериализовать хранимую модель проекта в ProjectModel."""
    return ProjectModel.model_validate(project.model)


def duplicate_project(db: Session, project: Project, name: str) -> Project:
    """Копия проекта (B2): модель целиком, сводка расчёта не переносится."""
    copy = Project(organization_id=project.organization_id, name=name, model=project.model)
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


# --- Субъекты анализа (Финанс-Аудит, продукт №2) ---

def create_audit_subject(db: Session, org_id: str, name: str,
                         model: AuditSubjectModel) -> AuditSubject:
    subject = AuditSubject(organization_id=org_id, name=name,
                           model=model.model_dump(mode="json"))
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


def list_audit_subjects(db: Session, org_id: str) -> list[AuditSubject]:
    return list(
        db.scalars(
            select(AuditSubject)
            .where(AuditSubject.organization_id == org_id)
            .order_by(AuditSubject.created_at.desc())
        )
    )


def get_audit_subject(db: Session, org_id: str, subject_id: str) -> AuditSubject | None:
    return db.scalar(
        select(AuditSubject).where(
            AuditSubject.id == subject_id, AuditSubject.organization_id == org_id
        )
    )


def update_audit_subject(db: Session, subject: AuditSubject, *, name: str | None = None,
                         model: AuditSubjectModel | None = None) -> AuditSubject:
    if name is not None:
        subject.name = name
    if model is not None:
        subject.model = model.model_dump(mode="json")
    db.commit()
    db.refresh(subject)
    return subject


def duplicate_audit_subject(db: Session, subject: AuditSubject, name: str) -> AuditSubject:
    """Копия субъекта: модель целиком, новое имя.

    Для аудита дубль уместнее, чем для проекта: повторная проверка той же фирмы через
    год начинается с прошлогоднего дела — реквизиты, методики и нормативы уже заведены,
    меняется только отчётность.
    """
    copy = AuditSubject(organization_id=subject.organization_id, name=name,
                        model=subject.model)
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


def delete_audit_subject(db: Session, subject: AuditSubject) -> None:
    db.delete(subject)
    db.commit()


def load_audit_model(subject: AuditSubject) -> AuditSubjectModel:
    return AuditSubjectModel.model_validate(subject.model)


# --- Сохранённые группы предприятий (Финанс-Аудит, v2) ---

def create_audit_group(db: Session, org_id: str, name: str, model: AuditGroupModel) -> AuditGroup:
    group = AuditGroup(organization_id=org_id, name=name, model=model.model_dump(mode="json"))
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def list_audit_groups(db: Session, org_id: str) -> list[AuditGroup]:
    return list(
        db.scalars(
            select(AuditGroup)
            .where(AuditGroup.organization_id == org_id)
            .order_by(AuditGroup.created_at.desc())
        )
    )


def get_audit_group(db: Session, org_id: str, group_id: str) -> AuditGroup | None:
    return db.scalar(
        select(AuditGroup).where(
            AuditGroup.id == group_id, AuditGroup.organization_id == org_id
        )
    )


def update_audit_group(db: Session, group: AuditGroup, *, name: str | None = None,
                       model: AuditGroupModel | None = None) -> AuditGroup:
    if name is not None:
        group.name = name
    if model is not None:
        group.model = model.model_dump(mode="json")
    db.commit()
    db.refresh(group)
    return group


def delete_audit_group(db: Session, group: AuditGroup) -> None:
    db.delete(group)
    db.commit()


def load_audit_group_model(group: AuditGroup) -> AuditGroupModel:
    return AuditGroupModel.model_validate(group.model)


# --- Версии проекта (пакет №8, gap 4.4) ---

#: Максимум версий на проект (защита хранилища; сверх — ошибка на уровне роутера).
MAX_VERSIONS_PER_PROJECT = 50


def count_versions(db: Session, project_id: str) -> int:
    return db.scalar(
        select(func.count()).select_from(ProjectVersion)
        .where(ProjectVersion.project_id == project_id)
    ) or 0


def create_version(db: Session, project: Project, label: str, *,
                   npv: str | None = None, irr_annual: str | None = None,
                   engine_version: str | None = None) -> ProjectVersion:
    """Снимок текущей модели проекта как именованная версия (+ сводка расчёта)."""
    version = ProjectVersion(
        organization_id=project.organization_id, project_id=project.id, label=label,
        model=project.model, npv=npv, irr_annual=irr_annual, engine_version=engine_version,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def list_versions(db: Session, org_id: str, project_id: str) -> list[ProjectVersion]:
    return list(
        db.scalars(
            select(ProjectVersion)
            .where(ProjectVersion.project_id == project_id,
                   ProjectVersion.organization_id == org_id)
            .order_by(ProjectVersion.created_at.desc())
        )
    )


def get_version(db: Session, org_id: str, project_id: str,
                version_id: str) -> ProjectVersion | None:
    return db.scalar(
        select(ProjectVersion).where(
            ProjectVersion.id == version_id,
            ProjectVersion.project_id == project_id,
            ProjectVersion.organization_id == org_id,
        )
    )


def delete_version(db: Session, version: ProjectVersion) -> None:
    db.delete(version)
    db.commit()


# --- Отраслевые ориентиры организации (свои, не рыночные) ---

def list_benchmarks(db: Session, org_id: str) -> list[IndustryBenchmark]:
    return list(
        db.scalars(
            select(IndustryBenchmark)
            .where(IndustryBenchmark.organization_id == org_id)
            .order_by(IndustryBenchmark.industry, IndustryBenchmark.metric)
        )
    )


def replace_benchmarks(db: Session, org_id: str,
                       rows: list[dict]) -> list[IndustryBenchmark]:
    """Заменить справочник ориентиров организации целиком.

    Справочник правится как таблица (добавили строку, поправили значение, убрали
    лишнее), поэтому и сохраняется целиком: пять отдельных вызовов на одно нажатие
    «Сохранить» дали бы частично применённый справочник при первой же ошибке сети.
    """
    for row in db.scalars(
        select(IndustryBenchmark).where(IndustryBenchmark.organization_id == org_id)
    ):
        db.delete(row)
    saved = [IndustryBenchmark(organization_id=org_id, industry=r["industry"],
                               metric=r["metric"], value=r["value"],
                               source=r.get("source", ""))
             for r in rows]
    db.add_all(saved)
    db.commit()
    return list_benchmarks(db, org_id)


# --- Версии дела (Финанс-Аудит): снимки модели проверки ---

#: Максимум версий на дело. Тот же предел, что у проекта: снимков в проверке столько же
#: по природе (итерация — приход документов), и второй предел спорил бы с первым.
MAX_VERSIONS_PER_SUBJECT = MAX_VERSIONS_PER_PROJECT


def count_audit_versions(db: Session, subject_id: str) -> int:
    return db.scalar(
        select(func.count()).select_from(AuditSubjectVersion)
        .where(AuditSubjectVersion.subject_id == subject_id)
    ) or 0


def create_audit_version(db: Session, subject: AuditSubject, label: str, *,
                         verdict: str | None = None, risk_flags: int | None = None,
                         equity_value: str | None = None) -> AuditSubjectVersion:
    """Снимок текущей модели дела как именованная версия (+ сводка на тот момент)."""
    version = AuditSubjectVersion(
        organization_id=subject.organization_id, subject_id=subject.id, label=label,
        model=subject.model, verdict=verdict, risk_flags=risk_flags,
        equity_value=equity_value,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def list_audit_versions(db: Session, org_id: str,
                        subject_id: str) -> list[AuditSubjectVersion]:
    return list(
        db.scalars(
            select(AuditSubjectVersion)
            .where(AuditSubjectVersion.subject_id == subject_id,
                   AuditSubjectVersion.organization_id == org_id)
            .order_by(AuditSubjectVersion.created_at.desc())
        )
    )


def get_audit_version(db: Session, org_id: str, subject_id: str,
                      version_id: str) -> AuditSubjectVersion | None:
    return db.scalar(
        select(AuditSubjectVersion).where(
            AuditSubjectVersion.id == version_id,
            AuditSubjectVersion.subject_id == subject_id,
            AuditSubjectVersion.organization_id == org_id,
        )
    )


def delete_audit_version(db: Session, version: AuditSubjectVersion) -> None:
    db.delete(version)
    db.commit()


def save_calc_summary(db: Session, project: Project, *, npv: Decimal,
                      irr_annual: Decimal | None, pb_months: int | None,
                      engine_version: str) -> None:
    """Сохранить сводку успешного расчёта (B1).

    Core-update с явным ``updated_at = Project.updated_at``: иначе onupdate
    сдвинул бы updated_at и проект сразу считался бы «изменён после расчёта».
    """
    db.execute(
        update(Project)
        .where(Project.id == project.id)
        .values(
            last_npv=str(npv),
            last_irr=None if irr_annual is None else str(irr_annual),
            last_pb_months=pb_months,
            last_engine_version=engine_version,
            last_calculated_at=datetime.now(timezone.utc),
            updated_at=Project.updated_at,
        )
    )
    db.commit()
    db.refresh(project)


# --- Холдинги (9.3) ---

def create_holding(db: Session, org_id: str, name: str) -> Holding:
    holding = Holding(organization_id=org_id, name=name)
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return holding


def list_holdings(db: Session, org_id: str) -> list[Holding]:
    return list(
        db.scalars(
            select(Holding).where(Holding.organization_id == org_id).order_by(Holding.created_at.desc())
        )
    )


def get_holding(db: Session, org_id: str, holding_id: str) -> Holding | None:
    return db.scalar(
        select(Holding).where(Holding.id == holding_id, Holding.organization_id == org_id)
    )


def delete_holding(db: Session, holding: Holding) -> None:
    db.delete(holding)
    db.commit()


def add_holding_member(db: Session, holding_id: str, project_id: str,
                       role: str = "subsidiary") -> HoldingMember:
    existing = db.scalar(
        select(HoldingMember).where(
            HoldingMember.holding_id == holding_id, HoldingMember.project_id == project_id
        )
    )
    if existing is not None:
        existing.role = role
        db.commit()
        db.refresh(existing)
        return existing
    member = HoldingMember(holding_id=holding_id, project_id=project_id, role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def list_holding_members(db: Session, holding_id: str) -> list[HoldingMember]:
    return list(
        db.scalars(select(HoldingMember).where(HoldingMember.holding_id == holding_id))
    )


def get_holding_member(db: Session, holding_id: str, project_id: str) -> HoldingMember | None:
    return db.scalar(
        select(HoldingMember).where(
            HoldingMember.holding_id == holding_id, HoldingMember.project_id == project_id
        )
    )


def remove_holding_member(db: Session, member: HoldingMember) -> None:
    db.delete(member)
    db.commit()


def save_holding_consolidation(db: Session, holding: Holding, *, npv: Decimal,
                               rate: Decimal) -> None:
    """Сохранить сводку последней консолидации холдинга (B3)."""
    holding.last_consolidation_npv = str(npv)
    holding.last_consolidation_rate = str(rate)
    holding.last_consolidation_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(holding)

# --- Журнал действий (152-ФЗ, ARCHITECTURE §4) ---

def log_user_action(db: Session, user, action: str, *, details: str = "") -> None:
    """Событие самого пользователя (вход, смена пароля) — в журналы **его** организаций.

    У журнала есть владелец-организация, а событие входа принадлежит человеку. Пишем его
    в каждую организацию, где он состоит: администратор обязан видеть, что происходит с
    доступом к **его** данным, а другого места у записи нет.

    Для **несуществующего** адреса не пишется ничего: журнала у него нет, а запись
    превратила бы систему в подсказчик «такой адрес у нас есть».
    """
    if user is None:
        return
    for membership in list_user_memberships(db, user.id):
        log_action(db, membership.organization_id, user, action, entity_type="user",
                   entity_id=user.id, entity_name=user.email, details=details)


def log_action(db: Session, org_id: str, user, action: str, *, entity_type: str = "",
               entity_id: str = "", entity_name: str = "", details: str = "") -> AuditLogEntry:
    """Записать действие в журнал организации.

    ``user`` может быть ``None`` (системное действие). Почта актора дублируется текстом:
    участника удалят, а журнал обязан отвечать «кто это сделал» и через год.

    Длинные поля обрезаются до размера колонки, а не роняют запрос: имя дела задаёт
    пользователь, и слишком длинное имя не повод потерять запись о его удалении.
    """
    entry = AuditLogEntry(
        organization_id=org_id,
        user_id=getattr(user, "id", None),
        actor_email=(getattr(user, "email", "") or "")[:255],
        action=action[:64],
        entity_type=entity_type[:32],
        entity_id=entity_id[:36],
        entity_name=entity_name[:255],
        details=details[:500],
    )
    db.add(entry)
    db.commit()
    return entry


def _audit_log_filtered(org_id: str, *, actor: str = "", action: str = "",
                        entity_type: str = "", since: datetime | None = None,
                        until: datetime | None = None, q: str = ""):
    """Условия отбора — общие для чтения и для счётчика.

    Иначе «показано 50 из 12 000» врало бы: счётчик считал бы весь журнал, а список —
    отобранное. Одно место условий делает эту ошибку невозможной.
    """
    stmt = select(AuditLogEntry).where(AuditLogEntry.organization_id == org_id)
    if actor:
        stmt = stmt.where(AuditLogEntry.actor_email == actor)
    if action:
        stmt = stmt.where(AuditLogEntry.action == action)
    if entity_type:
        stmt = stmt.where(AuditLogEntry.entity_type == entity_type)
    if since is not None:
        stmt = stmt.where(AuditLogEntry.created_at >= since)
    if until is not None:
        stmt = stmt.where(AuditLogEntry.created_at <= until)
    if q:
        # Поиск по тому, что человек помнит: имя сущности, кто сделал, примечание.
        like = f"%{q}%"
        stmt = stmt.where(
            AuditLogEntry.entity_name.ilike(like)
            | AuditLogEntry.actor_email.ilike(like)
            | AuditLogEntry.details.ilike(like)
        )
    return stmt


def list_audit_log(db: Session, org_id: str, limit: int = 200,
                   before: datetime | None = None, **filters) -> list[AuditLogEntry]:
    """Записи журнала организации, новые сверху; ``before`` — курсор постраничного чтения."""
    stmt = _audit_log_filtered(org_id, **filters)
    if before is not None:
        stmt = stmt.where(AuditLogEntry.created_at < before)
    stmt = stmt.order_by(AuditLogEntry.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars())


def count_audit_log(db: Session, org_id: str, **filters) -> int:
    """Сколько записей **под теми же условиями**, что и в списке."""
    inner = _audit_log_filtered(org_id, **filters).subquery()
    return int(db.execute(select(func.count()).select_from(inner)).scalar_one())


def audit_log_actors(db: Session, org_id: str) -> list[str]:
    """Кто вообще что-то делал в организации — для выбора в фильтре.

    Из **журнала**, а не из списка участников: удалённый сотрудник из участников исчез,
    а из журнала — нет, и отфильтровать его действия по-прежнему нужно.
    """
    rows = db.execute(
        select(AuditLogEntry.actor_email)
        .where(AuditLogEntry.organization_id == org_id, AuditLogEntry.actor_email != "")
        .distinct().order_by(AuditLogEntry.actor_email)
    ).scalars()
    return list(rows)


def audit_log_actions(db: Session, org_id: str) -> list[str]:
    """Какие действия встречались — чтобы фильтр предлагал существующее, а не весь каталог."""
    rows = db.execute(
        select(AuditLogEntry.action)
        .where(AuditLogEntry.organization_id == org_id)
        .distinct().order_by(AuditLogEntry.action)
    ).scalars()
    return list(rows)


# --- Служебный контур платформы (ADMIN-DECOMPOSITION.md, B1) ---
#
# Функции ниже читают **метаданные**: организации, состав, подписки, объёмы. Содержимого
# проектов и дел здесь нет и быть не должно (правило 6 плана): владелец SaaS, читающий
# финансовые модели клиентов, — ровно то, чего клиент опасается. Единственное, что
# служебный контур знает о проекте, — что он существует и когда его последний раз считали.

def list_organizations(db: Session, *, q: str = "", limit: int = 50,
                       offset: int = 0) -> list[Organization]:
    """Организации платформы, новые сверху; ``q`` — подстрока названия."""
    stmt = select(Organization)
    if q:
        stmt = stmt.where(Organization.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(Organization.created_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


def count_organizations(db: Session, *, q: str = "") -> int:
    """Сколько организаций **под тем же условием**, что и в списке."""
    stmt = select(func.count()).select_from(Organization)
    if q:
        stmt = stmt.where(Organization.name.ilike(f"%{q}%"))
    return int(db.scalar(stmt) or 0)


def org_volumes(db: Session, org_id: str) -> dict:
    """Объёмы организации: сколько чего заведено и когда последний раз считали.

    **Числа расчётов здесь нет.** Счётчика расчётов платформа не ведёт: расчёт зовётся
    при каждом открытии результатов, это чтение, и в журнал он не пишется (правило 5).
    Придумать число, глядя на журнал, значило бы выдать выгрузки за расчёты; вместо
    этого возвращается дата последнего расчёта — она есть в самих проектах.
    """
    last_calc = db.scalar(
        select(func.max(Project.last_calculated_at)).where(Project.organization_id == org_id)
    )
    last_seen = db.scalar(
        select(func.max(Membership.last_seen_at)).where(Membership.organization_id == org_id)
    )
    return {
        "projects": count_projects(db, org_id),
        "cases": count_audit_subjects(db, org_id),
        "groups": int(db.scalar(
            select(func.count()).select_from(AuditGroup)
            .where(AuditGroup.organization_id == org_id)) or 0),
        "holdings": int(db.scalar(
            select(func.count()).select_from(Holding)
            .where(Holding.organization_id == org_id)) or 0),
        "members": count_members(db, org_id),
        "members_blocked": int(db.scalar(
            select(func.count()).select_from(Membership)
            .where(Membership.organization_id == org_id,
                   Membership.blocked_at.is_not(None))) or 0),
        "last_calculated_at": last_calc,
        "last_seen_at": last_seen,
    }


def search_users(db: Session, *, q: str = "", limit: int = 50) -> list[User]:
    """Поиск пользователя по адресу или имени — вход в разбор обращения в поддержку."""
    stmt = select(User)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(User.email.ilike(like) | User.full_name.ilike(like))
    return list(db.execute(stmt.order_by(User.created_at.desc()).limit(limit)).scalars())


def set_staff(db: Session, user: User, *, is_staff: bool) -> User:
    """Назначить или снять признак сотрудника платформы.

    Вызывается **скриптом**, а не маршрутом API: эндпоинт, повышающий права, сам стал бы
    главной мишенью, и защищать его пришлось бы сильнее всего остального вместе взятого.
    """
    user.is_staff = is_staff
    db.commit()
    db.refresh(user)
    return user


def log_staff_action(db: Session, user, action: str, *, org_id: str = "",
                     org_name: str = "", details: str = "") -> StaffLogEntry:
    """Записать действие сотрудника платформы в **служебный** журнал.

    Визит к конкретному клиенту пишется дважды: сюда и в журнал самой организации
    (``log_action``). Два журнала отвечают на разные вопросы — «где сегодня был наш
    сотрудник» и «кто приходил ко мне», — и ни один из них не выводится из другого.
    """
    entry = StaffLogEntry(
        user_id=getattr(user, "id", None),
        actor_email=(getattr(user, "email", "") or "")[:255],
        action=action[:64],
        organization_id=org_id[:36],
        organization_name=org_name[:255],
        details=details[:500],
    )
    db.add(entry)
    db.commit()
    return entry


def list_staff_log(db: Session, limit: int = 200, *, actor: str = "",
                   org_id: str = "") -> list[StaffLogEntry]:
    """Служебный журнал, новые сверху. Как и журнал организации — только чтение."""
    stmt = select(StaffLogEntry)
    if actor:
        stmt = stmt.where(StaffLogEntry.actor_email == actor)
    if org_id:
        stmt = stmt.where(StaffLogEntry.organization_id == org_id)
    return list(db.execute(
        stmt.order_by(StaffLogEntry.created_at.desc()).limit(limit)).scalars())
