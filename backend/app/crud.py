"""CRUD-операции: организации, пользователи, членство, проекты.

Проекты изолированы по ``organization_id`` (мультиарендность, 6.2).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from calc_core import ProjectModel

from .db_models import Membership, Organization, Project, User


# --- Организации ---

def create_organization(db: Session, name: str) -> Organization:
    org = Organization(name=name)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def get_organization(db: Session, org_id: str) -> Organization | None:
    return db.get(Organization, org_id)


# --- Пользователи и членство ---

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_or_create_user(db: Session, email: str, full_name: str = "") -> User:
    user = get_user_by_email(db, email)
    if user is None:
        user = User(email=email, full_name=full_name)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def add_member(db: Session, org_id: str, email: str, full_name: str = "",
               role: str = "owner") -> Membership:
    user = get_or_create_user(db, email, full_name)
    existing = db.scalar(
        select(Membership).where(
            Membership.organization_id == org_id, Membership.user_id == user.id
        )
    )
    if existing is not None:
        return existing
    membership = Membership(organization_id=org_id, user_id=user.id, role=role)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


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
