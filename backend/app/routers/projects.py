"""REST-эндпоинты для проектов (персистентность 6.1 + изоляция по тенанту 6.2).

Все операции ограничены текущей организацией (``current_org_id``): проект из чужой
организации недоступен (404).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from calc_core import run
from calc_core.engine import ModelError

from .. import crud
from ..database import get_db
from ..db_models import Project
from ..deps import current_org_id
from ..schemas import (
    CalcResponse,
    ProjectCreate,
    ProjectOut,
    ProjectSummary,
    ProjectUpdate,
    to_response,
)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _summary(p: Project) -> ProjectSummary:
    return ProjectSummary(id=p.id, name=p.name, created_at=p.created_at, updated_at=p.updated_at)


def _out(p: Project) -> ProjectOut:
    return ProjectOut(id=p.id, name=p.name, created_at=p.created_at,
                      updated_at=p.updated_at, model=crud.load_model(p))


def _require(db: Session, org_id: str, project_id: str) -> Project:
    project = crud.get_project(db, org_id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return project


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, org_id: str = Depends(current_org_id),
                   db: Session = Depends(get_db)) -> ProjectOut:
    """Создать проект в текущей организации."""
    return _out(crud.create_project(db, org_id, body.name, body.model))


@router.get("", response_model=list[ProjectSummary])
def list_projects(org_id: str = Depends(current_org_id),
                  db: Session = Depends(get_db)) -> list[ProjectSummary]:
    """Список проектов организации (метаданные)."""
    return [_summary(p) for p in crud.list_projects(db, org_id)]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, org_id: str = Depends(current_org_id),
                db: Session = Depends(get_db)) -> ProjectOut:
    """Получить проект с моделью."""
    return _out(_require(db, org_id, project_id))


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate,
                   org_id: str = Depends(current_org_id),
                   db: Session = Depends(get_db)) -> ProjectOut:
    """Обновить имя и/или модель проекта."""
    project = _require(db, org_id, project_id)
    return _out(crud.update_project(db, project, name=body.name, model=body.model))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, org_id: str = Depends(current_org_id),
                   db: Session = Depends(get_db)) -> None:
    """Удалить проект."""
    crud.delete_project(db, _require(db, org_id, project_id))


@router.post("/{project_id}/calculate", response_model=CalcResponse)
def calculate_project(project_id: str, org_id: str = Depends(current_org_id),
                      db: Session = Depends(get_db)) -> CalcResponse:
    """Рассчитать сохранённый проект."""
    project = _require(db, org_id, project_id)
    try:
        result = run(crud.load_model(project))
    except ModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return to_response(result)
