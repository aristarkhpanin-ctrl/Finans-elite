"""PIC Holding (9.3): структура холдинга и сводный бюджет.

v0: персистентная группа проектов (головная + дочерние) и консолидированный отчёт
(построчная сумма, как Integrator). Межфирменное элиминирование (взаимные займы как
активы у кредитора) требует расширения базовой модели — ограничение v0.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from calc_core.integrator import consolidate_detailed

from .. import crud
from ..database import get_db
from ..db_models import Holding
from ..deps import require_permission
from ..rbac import Perm
from ..schemas import (
    ConsolidateResponse,
    HoldingConsolidationOut,
    HoldingCreate,
    HoldingMemberCreate,
    HoldingMemberOut,
    HoldingMemberPatch,
    HoldingOut,
    PerProjectOut,
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
    last = None
    if holding.last_consolidation_npv is not None and holding.last_consolidation_at is not None:
        last = HoldingConsolidationOut(
            npv=holding.last_consolidation_npv,
            rate=holding.last_consolidation_rate or "0",
            at=holding.last_consolidation_at,
        )
    return HoldingOut(
        id=holding.id, name=holding.name, created_at=holding.created_at,
        members=[HoldingMemberOut(project_id=m.project_id, role=m.role) for m in members],
        last_consolidation=last,
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


@router.patch("/{holding_id}/members/{project_id}", response_model=HoldingOut)
def patch_member_role(holding_id: str, project_id: str, body: HoldingMemberPatch,
                      org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
                      db: Session = Depends(get_db)) -> HoldingOut:
    """Изменить роль участника холдинга (parent | subsidiary)."""
    holding = _require(db, org_id, holding_id)
    if body.role not in ("parent", "subsidiary"):
        raise HTTPException(status_code=422, detail="Роль: parent | subsidiary")
    member = crud.get_holding_member(db, holding.id, project_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Проект не входит в холдинг")
    crud.add_holding_member(db, holding.id, project_id, body.role)  # upsert роли
    return _out(db, holding)


@router.delete("/{holding_id}/members/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(holding_id: str, project_id: str,
                  org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
                  db: Session = Depends(get_db)) -> None:
    """Исключить проект из холдинга (сам проект не удаляется)."""
    holding = _require(db, org_id, holding_id)
    member = crud.get_holding_member(db, holding.id, project_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Проект не входит в холдинг")
    crud.remove_holding_member(db, member)


# Ставка дисконтирования группы по умолчанию (integrator).
_DEFAULT_GROUP_RATE = Decimal("0.15")


@router.post("/{holding_id}/consolidate", response_model=ConsolidateResponse)
def consolidate_holding(holding_id: str,
                        group_discount_rate: Decimal = _DEFAULT_GROUP_RATE,
                        org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                        db: Session = Depends(get_db)) -> ConsolidateResponse:
    """Сводный бюджет холдинга (консолидация) + разбивка вклада по проектам (B3)."""
    holding = _require(db, org_id, holding_id)
    members = crud.list_holding_members(db, holding.id)
    if not members:
        raise HTTPException(status_code=422, detail="В холдинге нет проектов")
    models = []
    for m in members:
        project = crud.get_project(db, org_id, m.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Проект не найден: {m.project_id}")
        models.append((m, project, crud.load_model(project)))
    try:
        group, per = consolidate_detailed([md for _, _, md in models], group_discount_rate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    per_project = []
    for (member, project, _), res in zip(models, per, strict=True):
        per_project.append(PerProjectOut(
            project_id=member.project_id,
            name=project.name,
            role=member.role,
            npv=res.metrics.npv,
            irr_annual=res.metrics.irr_annual,
            revenue_total=sum(res.income["I1"], Decimal(0)),
            net_profit_total=sum(res.income["I28"], Decimal(0)),
        ))

    crud.save_holding_consolidation(db, holding, npv=group.metrics.npv, rate=group_discount_rate)
    base = to_response(group)
    return ConsolidateResponse(**base.model_dump(), per_project=per_project)
