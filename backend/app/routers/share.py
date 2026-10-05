"""Ссылка для инвестора или банка (пакет L, L4): управление и публичный просмотр.

Управление — внутри проекта, теми же правами, что правка (ссылка — дверь наружу).
Просмотр — **без входа**: показатели и отчёты снимка, бизнес-план в DOCX с пометкой
«копия для …»; каждое открытие — в журнал организации-отправителя.
"""
from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from calc_core import run
from calc_core.engine.errors import ModelError
from calc_core.models import ProjectModel
from calc_core.review import ReviewContext, run_review
from calc_core.review.opinion import build_opinion
from calc_core.version import ENGINE_VERSION

from .. import crud, share_links, usage
from ..database import get_db
from ..db_models import User
from ..deps import current_user, require_permission
from ..docgen import DOCX_MIME, build_business_plan_docx
from ..ratelimit import rate_limit
from ..rbac import Perm
from ..schemas import (
    SharedPlanOut,
    ShareLinkCreate,
    ShareLinkCreated,
    ShareLinkOut,
    ShareLinksOut,
    to_response,
)
from ..timefmt import day_utc
from .projects import _calc_summary

router = APIRouter(prefix="/api/v1", tags=["share"])

_public_limit = rate_limit("shared", limit=60, window_seconds=60)

#: Что сказано всегда — и отправителю при создании, и посетителю при открытии.
WHO_OPENED = ("Кто открывает ссылку, отправителю не известно — её могли переслать. В "
              "журнале организации видно, по какой ссылке и когда её открывали.")
SNAPSHOT = ("Это копия плана на момент отправки: правка проекта после отправки её не "
            "меняет.")
#: Что сказано отправителю над списком ссылок.
CLOSING = ("Закрытая ссылка гаснет сразу и навсегда. Строка остаётся в списке: кому и "
           "когда открывали план, видно и потом.")


def _project(db: Session, org_id: str, project_id: str):
    project = crud.get_project(db, org_id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return project


def _out(link, version_label: str, opens: tuple[int, datetime | None] | None) -> ShareLinkOut:
    count, last = opens or (0, None)
    aware = share_links.aware
    return ShareLinkOut(
        id=link.id, label=link.label, version_id=link.version_id,
        version_label=version_label, created_at=aware(link.created_at),
        created_by=link.created_by, expires_at=aware(link.expires_at),
        revoked_at=aware(link.revoked_at) if link.revoked_at else None,
        revoked_by=link.revoked_by, state=share_links.state(link), opens=count,
        last_opened_at=aware(last) if last else None)


@router.get("/projects/{project_id}/share-links", response_model=ShareLinksOut)
def list_share_links(project_id: str,
                     org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                     db: Session = Depends(get_db)) -> ShareLinksOut:
    """Ссылки проекта — и живые, и закрытые: «кому открывали» должно быть проверяемым."""
    _project(db, org_id, project_id)
    links = share_links.list_for(db, org_id, project_id)
    versions = {v.id: v.label for v in crud.list_versions(db, org_id, project_id)}
    counts = share_links.opens(db, org_id, [link.id for link in links])
    return ShareLinksOut(
        links=[_out(link, versions.get(link.version_id, "удалена"), counts.get(link.id))
               for link in links],
        notes=[WHO_OPENED, CLOSING])


@router.post("/projects/{project_id}/share-links", response_model=ShareLinkCreated,
             status_code=status.HTTP_201_CREATED)
def create_share_link(project_id: str, body: ShareLinkCreate,
                      org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
                      actor: User = Depends(current_user),
                      db: Session = Depends(get_db)) -> ShareLinkCreated:
    """Открыть снимок проекта по ссылке. Без ``version_id`` — снимок делается сейчас."""
    project = _project(db, org_id, project_id)
    label = body.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="Укажите, для кого ссылка — это имя "
                                                    "будет напечатано на копии.")
    if share_links.active_count(db, org_id, project_id) >= share_links.MAX_ACTIVE_PER_PROJECT:
        raise HTTPException(status_code=409, detail=(
            f"У проекта уже {share_links.MAX_ACTIVE_PER_PROJECT} живых ссылок — закройте "
            "ненужные: забытая открытая ссылка — это открытая дверь."))
    if body.version_id:
        version = crud.get_version(db, org_id, project_id, body.version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="Версия не найдена")
    else:
        if crud.count_versions(db, project_id) >= crud.MAX_VERSIONS_PER_PROJECT:
            raise HTTPException(status_code=409, detail=(
                f"Достигнут лимит версий на проект ({crud.MAX_VERSIONS_PER_PROJECT}): ссылка "
                "открывает снимок, а сделать его некуда. Удалите ненужные версии."))
        npv, irr, engine = _calc_summary(crud.load_model(project))
        version = crud.create_version(
            db, project, f"Отправлено: {label} ({date.today():%d.%m.%Y})",
            npv=npv, irr_annual=irr, engine_version=engine)
    days, clamp_note = share_links.clamp_days(body.days)
    link, token = share_links.create(
        db, project=project, version=version, label=label, days=days,
        created_by=actor.email, engine_version=version.engine_version or ENGINE_VERSION)
    crud.log_action(db, org_id, actor, "share.create", entity_type="share_link",
                    entity_id=link.id, entity_name=label,
                    details=f"проект «{project.name}», версия «{version.label}», до "
                            f"{day_utc(link.expires_at)}")
    usage.record(db, event="project.share", org_id=org_id, email=actor.email)
    notes = [n for n in (clamp_note,) if n] + [
        "Ссылка показывается один раз: платформа хранит только её отпечаток. Потеряли — "
        "закройте эту и сделайте новую.", SNAPSHOT, WHO_OPENED]
    base = _out(link, version.label, None)
    return ShareLinkCreated(**base.model_dump(), token=token, path=f"/s/{token}", notes=notes)


@router.delete("/projects/{project_id}/share-links/{link_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_link(project_id: str, link_id: str,
                      org_id: str = Depends(require_permission(Perm.SHARE_CLOSE)),
                      actor: User = Depends(current_user),
                      db: Session = Depends(get_db)) -> None:
    """Закрыть ссылку — сразу и навсегда. Строка остаётся: «кому открывали» проверяемо.

    Право своё (``share.close``), а не правка проекта: при неоплате организация в режиме
    чтения, но закрыть дверь наружу обязана мочь и тогда.
    """
    link = share_links.get(db, org_id, project_id, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    if link.revoked_at is None:
        share_links.revoke(db, link, by=actor.email)
        crud.log_action(db, org_id, actor, "share.revoke", entity_type="share_link",
                        entity_id=link.id, entity_name=link.label)


# --- Публичный просмотр (без входа) ---

def _opened(db: Session, token: str, what: str) -> share_links.Opened:
    opened = share_links.open_shared(db, token, what=what)
    if isinstance(opened, tuple):
        code, detail = opened
        raise HTTPException(status_code=code, detail=detail)
    usage.record(db, event="share.open", org_id=opened.link.organization_id)
    return opened


def _model(opened: share_links.Opened) -> ProjectModel:
    try:
        return ProjectModel.model_validate(opened.version.model)
    except ValueError as exc:
        raise HTTPException(status_code=410, detail=(
            "План по этой ссылке больше не открывается: формат модели с тех пор изменился. "
            "Попросите отправителя прислать новую ссылку.")) from exc


@router.get("/shared/{token}", response_model=SharedPlanOut,
            dependencies=[Depends(_public_limit)])
def shared_plan(token: str, db: Session = Depends(get_db)) -> SharedPlanOut:
    """Снимок плана по ссылке — показатели и отчёты (без входа)."""
    opened = _opened(db, token, "просмотр")
    model = _model(opened)
    try:
        result = run(model)
    except (ModelError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    link = opened.link
    notes = [SNAPSHOT]
    if link.engine_version and link.engine_version != ENGINE_VERSION:
        notes.append(f"План отправлен, когда методика расчёта была версии "
                     f"{link.engine_version}; сейчас — {ENGINE_VERSION}. Методика менялась, "
                     "и числа могли сдвинуться относительно отправленных.")
    notes.append(WHO_OPENED)
    return SharedPlanOut(
        project_name=opened.project.name, version_label=opened.version.label,
        shared_for=link.label, organization=opened.org_name,
        created_at=share_links.aware(link.created_at),
        expires_at=share_links.aware(link.expires_at), engine_then=link.engine_version,
        engine_now=ENGINE_VERSION,
        discount_rate_annual=str(model.settings.discount_rate_annual),
        foreign_code=(model.environment.currencies[1].code
                      if len(model.environment.currencies) > 1 else ""),
        discount_rate_annual_foreign=str(model.settings.discount_rate_annual_foreign),
        organization_logo=opened.logo.data_url if opened.logo else None,
        notes=notes, result=to_response(result))


@router.get("/shared/{token}/business-plan.docx", dependencies=[Depends(_public_limit)])
def shared_docx(token: str, db: Session = Depends(get_db)) -> Response:
    """Бизнес-план снимка в DOCX — с пометкой, для кого копия и до какого числа."""
    opened = _opened(db, token, "бизнес-план (DOCX)")
    model = _model(opened)
    try:
        result = run(model)
    except (ModelError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    review = run_review(ReviewContext(model=model, result=result))
    expires = share_links.aware(opened.link.expires_at)
    content = build_business_plan_docx(
        model, result, build_opinion(review, result), project_name=opened.project.name,
        shared_for=opened.link.label, shared_until=expires.date(), logo=opened.logo)
    filename = quote(f"{opened.project.name}.docx")
    return Response(content=content, media_type=DOCX_MIME, headers={
        "Content-Disposition":
            f"attachment; filename=\"business-plan.docx\"; filename*=UTF-8''{filename}"})
