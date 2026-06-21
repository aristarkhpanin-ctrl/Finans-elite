"""CRUD-операции: организации, пользователи, членство, проекты.

Проекты изолированы по ``organization_id`` (мультиарендность, 6.2).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from calc_core import ProjectModel

from .db_models import (
    Holding,
    HoldingMember,
    Membership,
    Organization,
    Payment,
    Project,
    Subscription,
    User,
)
from .plans import DEFAULT_PLAN


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

def get_subscription(db: Session, org_id: str) -> Subscription | None:
    return db.scalar(select(Subscription).where(Subscription.organization_id == org_id))


def set_plan(db: Session, org_id: str, plan_code: str, status: str = "active") -> Subscription:
    sub = get_subscription(db, org_id)
    if sub is None:
        sub = Subscription(organization_id=org_id, plan_code=plan_code, status=status)
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


def update_project(db: Session, project: Project, *, name: str | None = None,
                   model: ProjectModel | None = None) -> Project:
    if name is not None:
        project.name = name
    if model is not None:
        project.model = model.model_dump(mode="json")
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: Project) -> None:
    db.delete(project)
    db.commit()


def load_model(project: Project) -> ProjectModel:
    """Десериализовать хранимую модель проекта в ProjectModel."""
    return ProjectModel.model_validate(project.model)


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
