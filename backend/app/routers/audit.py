"""REST-эндпоинты Финанс-Аудит (продукт №2): субъекты анализа фактической отчётности.

Все операции ограничены текущей организацией (изоляция арендатора, как проекты):
субъект из чужой организации недоступен (404). Права переиспуют проектные (кто ведёт
проекты — ведёт и субъекты аудита).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..db_models import AuditSubject
from ..deps import require_permission
from ..rbac import Perm
from ..schemas import (
    AuditSubjectCreate,
    AuditSubjectOut,
    AuditSubjectSummary,
    AuditSubjectUpdate,
)

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def _summary(s: AuditSubject) -> AuditSubjectSummary:
    m = crud.load_audit_model(s)
    return AuditSubjectSummary(id=s.id, name=s.name, created_at=s.created_at,
                              updated_at=s.updated_at, n_periods=m.n, balanced=m.is_balanced())


def _out(s: AuditSubject) -> AuditSubjectOut:
    m = crud.load_audit_model(s)
    return AuditSubjectOut(id=s.id, name=s.name, created_at=s.created_at,
                          updated_at=s.updated_at, n_periods=m.n, balanced=m.is_balanced(),
                          model=m, balance_gap=m.balance_gap())


def _require(db: Session, org_id: str, subject_id: str) -> AuditSubject:
    subject = crud.get_audit_subject(db, org_id, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Субъект анализа не найден")
    return subject


@router.post("/subjects", response_model=AuditSubjectOut, status_code=status.HTTP_201_CREATED)
def create_subject(body: AuditSubjectCreate,
                   org_id: str = Depends(require_permission(Perm.PROJECT_CREATE)),
                   db: Session = Depends(get_db)) -> AuditSubjectOut:
    """Создать субъект анализа в текущей организации."""
    return _out(crud.create_audit_subject(db, org_id, body.name, body.model))


@router.get("/subjects", response_model=list[AuditSubjectSummary])
def list_subjects(org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                  db: Session = Depends(get_db)) -> list[AuditSubjectSummary]:
    """Список субъектов анализа организации (метаданные)."""
    return [_summary(s) for s in crud.list_audit_subjects(db, org_id)]


@router.get("/subjects/{subject_id}", response_model=AuditSubjectOut)
def get_subject(subject_id: str,
                org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                db: Session = Depends(get_db)) -> AuditSubjectOut:
    """Получить субъект с моделью и сходимостью баланса по периодам."""
    return _out(_require(db, org_id, subject_id))


@router.put("/subjects/{subject_id}", response_model=AuditSubjectOut)
def update_subject(subject_id: str, body: AuditSubjectUpdate,
                   org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
                   db: Session = Depends(get_db)) -> AuditSubjectOut:
    """Обновить имя и/или модель субъекта."""
    subject = _require(db, org_id, subject_id)
    return _out(crud.update_audit_subject(db, subject, name=body.name, model=body.model))


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: str,
                   org_id: str = Depends(require_permission(Perm.PROJECT_DELETE)),
                   db: Session = Depends(get_db)) -> None:
    """Удалить субъект анализа."""
    crud.delete_audit_subject(db, _require(db, org_id, subject_id))
