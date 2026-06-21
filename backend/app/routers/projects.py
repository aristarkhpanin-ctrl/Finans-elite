"""REST-эндпоинты для проектов (персистентность 6.1 + изоляция по тенанту 6.2).

Все операции ограничены текущей организацией (``current_org_id``): проект из чужой
организации недоступен (404).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from calc_core import run
from calc_core.engine import ModelError
from calc_core.montecarlo import (
    Distribution,
    MonteCarloConfig,
    UncertainParam,
    run_monte_carlo,
)
from calc_core.sensitivity import SENSITIVITY_PARAMS, run_sensitivity

from .. import billing, crud
from ..database import get_db
from ..db_models import Project
from ..deps import require_permission
from ..rbac import Perm
from ..schemas import (
    CalcResponse,
    MonteCarloRequest,
    MonteCarloResponse,
    ProjectCreate,
    ProjectOut,
    ProjectSummary,
    ProjectUpdate,
    SensitivityPointOut,
    SensitivityRequest,
    SensitivityResponse,
    to_response,
)

# Лимит итераций для синхронного Монте-Карло (большие N — фоновой задачей, ARCHITECTURE §9).
_MAX_MC_ITERATIONS = 2000

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
def create_project(body: ProjectCreate,
                   org_id: str = Depends(require_permission(Perm.PROJECT_CREATE)),
                   db: Session = Depends(get_db)) -> ProjectOut:
    """Создать проект в текущей организации (право project.create; учёт квоты тарифа)."""
    billing.ensure_project_quota(db, org_id)
    return _out(crud.create_project(db, org_id, body.name, body.model))


@router.get("", response_model=list[ProjectSummary])
def list_projects(org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                  db: Session = Depends(get_db)) -> list[ProjectSummary]:
    """Список проектов организации (метаданные)."""
    return [_summary(p) for p in crud.list_projects(db, org_id)]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str,
                org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                db: Session = Depends(get_db)) -> ProjectOut:
    """Получить проект с моделью."""
    return _out(_require(db, org_id, project_id))


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate,
                   org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
                   db: Session = Depends(get_db)) -> ProjectOut:
    """Обновить имя и/или модель проекта (право project.update)."""
    project = _require(db, org_id, project_id)
    return _out(crud.update_project(db, project, name=body.name, model=body.model))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str,
                   org_id: str = Depends(require_permission(Perm.PROJECT_DELETE)),
                   db: Session = Depends(get_db)) -> None:
    """Удалить проект (право project.delete)."""
    crud.delete_project(db, _require(db, org_id, project_id))


@router.post("/{project_id}/calculate", response_model=CalcResponse)
def calculate_project(project_id: str,
                      org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                      db: Session = Depends(get_db)) -> CalcResponse:
    """Рассчитать сохранённый проект (право project.calculate)."""
    project = _require(db, org_id, project_id)
    try:
        result = run(crud.load_model(project))
    except (ModelError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return to_response(result)


@router.post("/{project_id}/sensitivity", response_model=SensitivityResponse)
def sensitivity(project_id: str, body: SensitivityRequest,
                org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                db: Session = Depends(get_db)) -> SensitivityResponse:
    """Анализ чувствительности: варьировать параметр и наблюдать NPV/IRR."""
    if body.param not in SENSITIVITY_PARAMS:
        raise HTTPException(status_code=422,
                            detail=f"Неизвестный параметр. Доступны: {sorted(SENSITIVITY_PARAMS)}")
    project = _require(db, org_id, project_id)
    try:
        points = run_sensitivity(crud.load_model(project), body.param, body.factors)
    except ModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SensitivityResponse(
        param=body.param,
        points=[SensitivityPointOut(factor=p.factor, npv=p.npv, irr_annual=p.irr_annual)
                for p in points],
    )


@router.post("/{project_id}/monte-carlo", response_model=MonteCarloResponse)
def monte_carlo(project_id: str, body: MonteCarloRequest,
                org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                db: Session = Depends(get_db)) -> MonteCarloResponse:
    """Анализ Монте-Карло: статистика NPV и вероятность NPV>0 (синхронно, с лимитом N)."""
    if not 1 <= body.iterations <= _MAX_MC_ITERATIONS:
        raise HTTPException(status_code=422,
                            detail=f"iterations должно быть от 1 до {_MAX_MC_ITERATIONS}")
    config = MonteCarloConfig(
        iterations=body.iterations,
        seed=body.seed,
        uncertain=[UncertainParam(param=u.param, distribution=Distribution(
            kind=u.distribution.kind, low=u.distribution.low, high=u.distribution.high,
            mean=u.distribution.mean, std=u.distribution.std, mode=u.distribution.mode))
            for u in body.uncertain],
    )
    project = _require(db, org_id, project_id)
    try:
        res = run_monte_carlo(crud.load_model(project), config)
    except (ModelError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MonteCarloResponse(
        iterations=res.iterations, npv_mean=res.npv_mean, npv_std=res.npv_std,
        npv_min=res.npv_min, npv_max=res.npv_max, npv_p10=res.npv_p10,
        npv_p50=res.npv_p50, npv_p90=res.npv_p90,
        probability_npv_positive=res.probability_npv_positive,
    )
