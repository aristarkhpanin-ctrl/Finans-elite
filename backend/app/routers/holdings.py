"""PIC Holding (9.3): структура холдинга и сводный бюджет.

v0: персистентная группа проектов (головная + дочерние) и консолидированный отчёт
(построчная сумма, как Integrator). Межфирменное элиминирование (взаимные займы как
активы у кредитора) требует расширения базовой модели — ограничение v0.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from calc_core.integrator import consolidate

from .. import crud
from ..database import get_db
from ..db_models import Holding
from ..deps import current_org_id, require_permission
from ..rbac import Perm
from ..schemas import (
    CalcResponse,
    HoldingCreate,
    HoldingMemberCreate,
    HoldingMemberOut,
    HoldingOut,
    to_response,
)

router = APIRouter(prefix="/api/v1/holdings", tags=["holdings"])


def _require(db: Session, org_id: str, holding_id: str) -> Holding:
    holding = crud.get_holding(db, org_id, holding_id)
    if holding is None:
        raise HTTPException(status_code=404, detail="Холдинг не найден")
    return holding


def _out(db: Session, holding: Holding) -> HoldingOut:
    members = crud.list_holding_members(db, holding.id)
    return HoldingOut(
        id=holding.id, name=holding.name, created_at=holding.created_at,
        members=[HoldingMemberOut(project_id=m.project_id, role=m.role) for m in members],
    )


@router.post("", response_model=HoldingOut, status_code=status.HTTP_201_CREATED)
def create_holding(body: HoldingCreate,
                   org_id: str = Depends(require_permission(Perm.PROJECT_CREATE)),
                   db: Session = Depends(get_db)) -> HoldingOut:
    return _out(db, crud.create_holding(db, org_id, body.name))


@router.get("", response_model=list[HoldingOut])
def list_holdings(org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                  db: Session = Depends(get_db)) -> list[HoldingOut]:
    return [_out(db, h) for h in crud.list_holdings(db, org_id)]


@router.get("/{holding_id}", response_model=HoldingOut)
def get_holding(holding_id: str, org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                db: Session = Depends(get_db)) -> HoldingOut:
    return _out(db, _require(db, org_id, holding_id))


@router.delete("/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holding(holding_id: str, org_id: str = Depends(require_permission(Perm.PROJECT_DELETE)),
                   db: Session = Depends(get_db)) -> None:
    crud.delete_holding(db, _require(db, org_id, holding_id))


@router.post("/{holding_id}/members", response_model=HoldingOut, status_code=status.HTTP_201_CREATED)
def add_member(holding_id: str, body: HoldingMemberCreate,
               org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
               db: Session = Depends(get_db)) -> HoldingOut:
    holding = _require(db, org_id, holding_id)
    # проект должен принадлежать организации
    if crud.get_project(db, org_id, body.project_id) is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    if body.role not in ("parent", "subsidiary"):
        raise HTTPException(status_code=422, detail="Роль: parent | subsidiary")
    crud.add_holding_member(db, holding.id, body.project_id, body.role)
    return _out(db, holding)


@router.post("/{holding_id}/consolidate", response_model=CalcResponse)
def consolidate_holding(holding_id: str,
                        org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                        db: Session = Depends(get_db)) -> CalcResponse:
    """Сводный бюджет холдинга (консолидация отчётов всех участников)."""
    holding = _require(db, org_id, holding_id)
    members = crud.list_holding_members(db, holding.id)
    if not members:
        raise HTTPException(status_code=422, detail="В холдинге нет проектов")
    models = []
    for m in members:
        project = crud.get_project(db, org_id, m.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Проект не найден: {m.project_id}")
        models.append(crud.load_model(project))
    try:
        result = consolidate(models)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return to_response(result)
