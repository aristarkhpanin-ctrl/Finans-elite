"""Integrator (9.2): консолидация нескольких проектов организации в группу."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from calc_core.integrator import consolidate

from .. import crud
from ..database import get_db
from ..deps import require_permission
from ..rbac import Perm
from ..schemas import CalcResponse, ConsolidateRequest, to_response

router = APIRouter(prefix="/api/v1/integrator", tags=["integrator"])


@router.post("/consolidate", response_model=CalcResponse)
def consolidate_projects(body: ConsolidateRequest,
                         org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                         db: Session = Depends(get_db)) -> CalcResponse:
    """Сводный результат по набору проектов организации (построчная сумма отчётов)."""
    if not body.project_ids:
        raise HTTPException(status_code=422, detail="Не указаны проекты")
    models = []
    for pid in body.project_ids:
        project = crud.get_project(db, org_id, pid)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Проект не найден: {pid}")
        models.append(crud.load_model(project))
    try:
        result = consolidate(models, body.group_discount_rate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return to_response(result)
