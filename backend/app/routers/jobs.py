"""Опрос статуса фоновых задач анализа (Celery)."""
from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, job_state
from ..celery_app import celery_app
from ..database import get_db
from ..deps import current_org_id
from ..schemas import JobStatusResponse, MonteCarloResponse

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


def fetch_state(job_id: str) -> tuple[str, object]:
    """Спросить Celery о задаче. Одна дверь на клиентский и служебный маршруты (F3):
    вторая обёртка вокруг `AsyncResult` однажды забыла бы ловить отказ брокера."""
    res = AsyncResult(job_id, app=celery_app)
    return res.state, res.result


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str, org_id: str = Depends(current_org_id),
               db: Session = Depends(get_db)) -> JobStatusResponse:
    """Статус (и результат) фоновой задачи. Доступна только своему арендатору.

    **Недоступный брокер больше не превращается в 500.** Раньше запрос к упавшему
    хранилищу результатов давал исключение, и клиент видел «не удалось загрузить» — то
    есть сообщение о поломке продукта там, где замолчало соседнее хозяйство. Теперь
    статус ``unknown`` с названной причиной (F3): молчание сети — не отказ задачи.
    """
    job = crud.get_analysis_job(db, job_id)
    if job is None or job.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    state, result = job_state.poll(job_id, fetch_state)
    verdict = job_state.interpret(state, created_at=job.created_at,
                                  error=str(result) if result is not None else "")
    if verdict.status == "success":
        return JobStatusResponse(job_id=job_id, status=verdict.status,
                                 result=MonteCarloResponse(**result))  # type: ignore[arg-type]
    if verdict.status == "failure":
        return JobStatusResponse(job_id=job_id, status=verdict.status,
                                 error=verdict.error)
    return JobStatusResponse(job_id=job_id, status=verdict.status, note=verdict.note)
