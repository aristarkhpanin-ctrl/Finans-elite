"""REST-эндпоинты для проектов (персистентность 6.1 + изоляция по тенанту 6.2).

Все операции ограничены текущей организацией (``current_org_id``): проект из чужой
организации недоступен (404).
"""
from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from calc_core import ProjectModel, run
from calc_core.engine import ModelError
from calc_core.engine.calendar import compute_budget
from calc_core.montecarlo import run_monte_carlo
from calc_core.review import ReviewContext, run_review
from calc_core.review.opinion import build_opinion
from calc_core.sensitivity import SENSITIVITY_PARAMS, run_sensitivity
from calc_core.whatif import Scenario, ScenarioAdjustment, run_what_if

from .. import billing, crud
from ..analysis_service import build_mc_config
from ..database import get_db
from ..db_models import Project
from ..deps import require_permission
from ..docgen import DOCX_MIME, build_business_plan_docx
from ..rbac import Perm
from ..schemas import (
    BudgetOut,
    CalcResponse,
    FinalizeRequest,
    FinalizeResponse,
    JobSubmitResponse,
    LastCalcOut,
    MetricChangeOut,
    ModelChangeOut,
    MonteCarloRequest,
    MonteCarloResponse,
    ProjectCreate,
    ProjectOut,
    ProjectSummary,
    ProjectUpdate,
    ReviewResponse,
    ScenarioResultOut,
    SensitivityPointOut,
    SensitivityRequest,
    SensitivityResponse,
    VersionCreate,
    VersionDiffOut,
    VersionOut,
    VersionSummary,
    WhatIfRequest,
    WhatIfResponse,
    budget_response,
    monte_carlo_response,
    review_response,
    to_response,
)
from ..tasks import monte_carlo_task
from ..versioning import diff_metrics, diff_models

# Лимит итераций для синхронного Монте-Карло (большие N — фоновой задачей, ARCHITECTURE §9).
_MAX_MC_ITERATIONS = 2000

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _last_calc(p: Project) -> LastCalcOut | None:
    if p.last_npv is None or p.last_calculated_at is None or p.last_engine_version is None:
        return None
    return LastCalcOut(npv=p.last_npv, irr_annual=p.last_irr, pb_months=p.last_pb_months,
                       engine_version=p.last_engine_version, calculated_at=p.last_calculated_at)


def _is_stale(p: Project) -> bool:
    return p.last_calculated_at is None or p.updated_at > p.last_calculated_at


def _summary(p: Project) -> ProjectSummary:
    return ProjectSummary(id=p.id, name=p.name, created_at=p.created_at, updated_at=p.updated_at,
                          last_calc=_last_calc(p), is_stale=_is_stale(p),
                          status=p.status, finalized_at=p.finalized_at)


def _finalized_review(p: Project) -> ReviewResponse | None:
    return ReviewResponse.model_validate(p.finalized_review) if p.finalized_review else None


def _finalized_drift(p: Project) -> bool:
    """Финализирован, но модель с тех пор изменилась (отпечаток не совпадает)."""
    if p.status != "finalized" or p.finalized_model_hash is None:
        return False
    return crud.model_hash(p.model) != p.finalized_model_hash


def _out(p: Project) -> ProjectOut:
    return ProjectOut(id=p.id, name=p.name, created_at=p.created_at,
                      updated_at=p.updated_at, model=crud.load_model(p),
                      last_calc=_last_calc(p), is_stale=_is_stale(p),
                      status=p.status, finalized_at=p.finalized_at,
                      finalized_review=_finalized_review(p), finalized_drift=_finalized_drift(p))


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


@router.post("/{project_id}/duplicate", response_model=ProjectOut,
             status_code=status.HTTP_201_CREATED)
def duplicate_project(project_id: str,
                      org_id: str = Depends(require_permission(Perm.PROJECT_CREATE)),
                      db: Session = Depends(get_db)) -> ProjectOut:
    """Дублировать проект (B2): модель целиком, имя «{name} (копия)», квота как в create."""
    project = _require(db, org_id, project_id)
    billing.ensure_project_quota(db, org_id)
    return _out(crud.duplicate_project(db, project, f"{project.name} (копия)"))


@router.post("/{project_id}/calculate", response_model=CalcResponse)
def calculate_project(project_id: str,
                      org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                      db: Session = Depends(get_db)) -> CalcResponse:
    """Рассчитать сохранённый проект (право project.calculate); сводка — на проект (B1)."""
    project = _require(db, org_id, project_id)
    try:
        result = run(crud.load_model(project))
    except (ModelError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    crud.save_calc_summary(db, project, npv=result.metrics.npv,
                           irr_annual=result.metrics.irr_annual,
                           pb_months=result.metrics.pb_months,
                           engine_version=result.engine_version)
    return to_response(result)


@router.get("/{project_id}/budget", response_model=BudgetOut)
def project_budget(project_id: str,
                   org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                   db: Session = Depends(get_db)) -> BudgetOut:
    """Смета по этапам календарного плана: строки, помесячный график, итог.

    Считается прямо из модели (без полного расчёта отчётов) — для быстрого предпросмотра
    сметы в редакторе календарного плана.
    """
    project = _require(db, org_id, project_id)
    model = crud.load_model(project)
    return budget_response(compute_budget(model, model.n))


@router.get("/{project_id}/review", response_model=ReviewResponse)
def review_project(project_id: str, deep: bool = False,
                   org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                   db: Session = Depends(get_db)) -> ReviewResponse:
    """Ревью бизнес-плана (Ф10): детерминированные находки и рекомендации по итогам расчёта.

    ``deep=true`` дополнительно прогоняет стохастику (Монте-Карло + чувствительность) для
    категории «дивергенция» (план ↔ вероятное будущее) — дороже, но полнее.
    """
    project = _require(db, org_id, project_id)
    model = crud.load_model(project)
    try:
        result = run(model)
    except (ModelError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    review = run_review(ReviewContext(model=model, result=result), deep=deep)
    return review_response(review, deep=deep, opinion=build_opinion(review, result))


@router.get("/{project_id}/business-plan.docx")
def business_plan_docx(project_id: str,
                       org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                       db: Session = Depends(get_db)) -> Response:
    """DOCX-бизнес-план (пакет №5, Q5): титул, заключение, показатели, разделы, отчёты.

    Считает проект на лету (как /calculate, но без записи сводки); заключение — быстрое
    ревью без стохастики. Право ``project.read`` — документ лишь отражает модель.
    """
    project = _require(db, org_id, project_id)
    model = crud.load_model(project)
    try:
        result = run(model)
    except (ModelError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    review = run_review(ReviewContext(model=model, result=result))
    content = build_business_plan_docx(model, result, build_opinion(review, result),
                                       project_name=project.name)
    filename = quote(f"{project.name}.docx")
    return Response(
        content=content,
        media_type=DOCX_MIME,
        headers={"Content-Disposition":
                 f"attachment; filename=\"business-plan.docx\"; filename*=UTF-8''{filename}"},
    )


@router.post("/{project_id}/finalize", response_model=FinalizeResponse)
def finalize_project(project_id: str, body: FinalizeRequest,
                     org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
                     db: Session = Depends(get_db)) -> FinalizeResponse:
    """Финализировать план — гейт ревью (Ф10, решение Q4: ревью перед финализацией).

    Прогоняет глубокое ревью. Если есть risk-находки и ``acknowledge=false`` — 409 (гейт
    не пройден), ревью возвращается в ``detail``. При ``acknowledge=true`` (или без risk)
    проект помечается ``finalized`` со снимком ревью и отпечатком модели. Warning/info
    финализации не мешают.
    """
    project = _require(db, org_id, project_id)
    model = crud.load_model(project)
    try:
        result = run(model)
    except (ModelError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    review = run_review(ReviewContext(model=model, result=result), deep=True)
    payload = review_response(review, deep=True, opinion=build_opinion(review, result))
    if review.counts.get("risk", 0) > 0 and not body.acknowledge:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "review_has_risks",
                    "message": "План содержит risk-находки; для финализации подтвердите "
                               "их осознание (acknowledge=true).",
                    "review": payload.model_dump(mode="json")},
        )
    finalized = crud.finalize_project(db, project, payload.model_dump(mode="json"))
    assert finalized.finalized_at is not None  # только что установлено в finalize_project
    return FinalizeResponse(status=finalized.status, finalized_at=finalized.finalized_at,
                            review=payload)


# --- Версии проекта (пакет №8, gap 4.4) ---

def _version_summary(v) -> VersionSummary:
    return VersionSummary(id=v.id, label=v.label, created_at=v.created_at,
                          npv=v.npv, irr_annual=v.irr_annual, engine_version=v.engine_version)


def _version_out(v) -> VersionOut:
    return VersionOut(id=v.id, label=v.label, created_at=v.created_at,
                      npv=v.npv, irr_annual=v.irr_annual, engine_version=v.engine_version,
                      model=ProjectModel.model_validate(v.model))


def _calc_summary(model: ProjectModel) -> tuple[str | None, str | None, str | None]:
    """Сводка расчёта для снимка (NPV/IRR/движок); при ошибке модели — нули (снимок всё равно валиден)."""
    try:
        result = run(model)
    except (ModelError, ValueError):
        return None, None, None
    irr = result.metrics.irr_annual
    return str(result.metrics.npv), (str(irr) if irr is not None else None), result.engine_version


def _require_version(db: Session, org_id: str, project_id: str, version_id: str):
    version = crud.get_version(db, org_id, project_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Версия не найдена")
    return version


@router.post("/{project_id}/versions", response_model=VersionSummary,
             status_code=status.HTTP_201_CREATED)
def create_version(project_id: str, body: VersionCreate,
                   org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
                   db: Session = Depends(get_db)) -> VersionSummary:
    """Снимок текущей модели как именованная версия (со сводкой расчёта)."""
    project = _require(db, org_id, project_id)
    if crud.count_versions(db, project_id) >= crud.MAX_VERSIONS_PER_PROJECT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Достигнут лимит версий на проект ({crud.MAX_VERSIONS_PER_PROJECT}). "
                   "Удалите ненужные версии.")
    npv, irr, engine_version = _calc_summary(crud.load_model(project))
    label = body.label.strip() or f"Версия от {project.updated_at:%d.%m.%Y %H:%M}"
    version = crud.create_version(db, project, label, npv=npv, irr_annual=irr,
                                  engine_version=engine_version)
    return _version_summary(version)


@router.get("/{project_id}/versions", response_model=list[VersionSummary])
def list_versions(project_id: str,
                  org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                  db: Session = Depends(get_db)) -> list[VersionSummary]:
    """Список версий проекта (метаданные, новейшие сверху)."""
    _require(db, org_id, project_id)
    return [_version_summary(v) for v in crud.list_versions(db, org_id, project_id)]


@router.get("/{project_id}/versions/{version_id}", response_model=VersionOut)
def get_version(project_id: str, version_id: str,
                org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                db: Session = Depends(get_db)) -> VersionOut:
    """Версия с полной моделью снимка."""
    _require(db, org_id, project_id)
    return _version_out(_require_version(db, org_id, project_id, version_id))


@router.delete("/{project_id}/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(project_id: str, version_id: str,
                   org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
                   db: Session = Depends(get_db)) -> None:
    """Удалить версию."""
    _require(db, org_id, project_id)
    crud.delete_version(db, _require_version(db, org_id, project_id, version_id))


@router.get("/{project_id}/versions/{version_id}/diff", response_model=VersionDiffOut)
def diff_version(project_id: str, version_id: str, against: str = "current",
                 org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                 db: Session = Depends(get_db)) -> VersionDiffOut:
    """Анализ изменений версии относительно другой версии или текущей модели.

    ``against`` — id другой версии либо ``current`` (рабочая модель проекта). old = эта
    версия, new = ``against``: «что изменилось от снимка к сравниваемому состоянию».
    """
    project = _require(db, org_id, project_id)
    base = _require_version(db, org_id, project_id, version_id)
    if against == "current":
        against_model = project.model
    else:
        against_model = _require_version(db, org_id, project_id, against).model

    changes, truncated = diff_models(base.model, against_model)
    metric_changes: list[MetricChangeOut] = []
    try:
        base_result = run(ProjectModel.model_validate(base.model))
        against_result = run(ProjectModel.model_validate(against_model))
        metric_changes = [
            MetricChangeOut(key=c.key, label=c.label, old=c.old, new=c.new)
            for c in diff_metrics(base_result, against_result)
        ]
    except (ModelError, ValueError):
        metric_changes = []       # одна из моделей не считается → только диф модели

    return VersionDiffOut(
        base_id=version_id, against=against,
        model_changes=[ModelChangeOut(path=c.path, kind=c.kind, old=c.old, new=c.new)
                       for c in changes],
        model_changes_truncated=truncated,
        metric_changes=metric_changes,
    )


@router.post("/{project_id}/versions/{version_id}/restore", response_model=ProjectOut)
def restore_version(project_id: str, version_id: str,
                    org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
                    db: Session = Depends(get_db)) -> ProjectOut:
    """Восстановить модель версии в рабочий проект (статус → draft, гейт сбрасывается)."""
    project = _require(db, org_id, project_id)
    version = _require_version(db, org_id, project_id, version_id)
    updated = crud.update_project(db, project, model=ProjectModel.model_validate(version.model))
    return _out(updated)


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
    project = _require(db, org_id, project_id)
    try:
        res = run_monte_carlo(crud.load_model(project), build_mc_config(body))
    except (ModelError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return monte_carlo_response(res)


@router.post("/{project_id}/monte-carlo/async", response_model=JobSubmitResponse,
             status_code=status.HTTP_202_ACCEPTED)
def monte_carlo_async(project_id: str, body: MonteCarloRequest,
                      org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                      db: Session = Depends(get_db)) -> JobSubmitResponse:
    """Поставить Монте-Карло в очередь (фоновый воркер). Опрос — GET /analysis/jobs/{id}."""
    if not 1 <= body.iterations <= _MAX_MC_ITERATIONS:
        raise HTTPException(status_code=422,
                            detail=f"iterations должно быть от 1 до {_MAX_MC_ITERATIONS}")
    project = _require(db, org_id, project_id)
    job_id = uuid.uuid4().hex
    crud.create_analysis_job(db, job_id, org_id, project_id, "monte_carlo")
    monte_carlo_task.apply_async(
        args=[project.model, body.model_dump(mode="json")], task_id=job_id,
    )
    return JobSubmitResponse(job_id=job_id)


@router.post("/{project_id}/what-if", response_model=WhatIfResponse)
def what_if(project_id: str, body: WhatIfRequest,
            org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
            db: Session = Depends(get_db)) -> WhatIfResponse:
    """What-If: сравнить базовый и заданные сценарии по показателям эффективности."""
    scenarios = [
        Scenario(name=s.name,
                 adjustments=[ScenarioAdjustment(param=a.param, factor=a.factor) for a in s.adjustments])
        for s in body.scenarios
    ]
    project = _require(db, org_id, project_id)
    try:
        results = run_what_if(crud.load_model(project), scenarios, include_base=body.include_base)
    except (ModelError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WhatIfResponse(scenarios=[
        ScenarioResultOut(name=r.name, npv=r.npv, irr_annual=r.irr_annual, pi=r.pi, pb_months=r.pb_months)
        for r in results
    ])
