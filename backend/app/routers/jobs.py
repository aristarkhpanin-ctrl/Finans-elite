"""Опрос статуса фоновых задач анализа (Celery)."""
from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud
from ..celery_app import celery_app
from ..database import get_db
from ..deps import current_org_id
from ..schemas import JobStatusResponse, MonteCarloResponse

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

# Состояния Celery → наш статус (прочие: PENDING/RETRY → «в очереди»).
_STATE_MAP = {"SUCCESS": "success", "FAILURE": "failure", "STARTED": "running"}


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str, org_id: str = Depends(current_org_id),
               db: Session = Depends(get_db)) -> JobStatusResponse:
    """Статус (и результат) фоновой задачи. Доступна только своему арендатору."""
    job = crud.get_analysis_job(db, job_id)
    if job is None or job.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    res = AsyncResult(job_id, app=celery_app)
    status = _STATE_MAP.get(res.state, "pending")
    if status == "success":
        return JobStatusResponse(job_id=job_id, status=status,
                                 result=MonteCarloResponse(**res.result))
    if status == "failure":
        return JobStatusResponse(job_id=job_id, status=status, error=str(res.result))
    return JobStatusResponse(job_id=job_id, status=status)
