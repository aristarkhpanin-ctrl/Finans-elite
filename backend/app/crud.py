"""CRUD-операции над проектами."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from calc_core import ProjectModel

from .db_models import Project


def create_project(db: Session, name: str, model: ProjectModel) -> Project:
    project = Project(name=name, model=model.model_dump(mode="json"))
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.created_at.desc())))


def get_project(db: Session, project_id: str) -> Project | None:
    return db.get(Project, project_id)


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
