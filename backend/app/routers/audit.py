"""REST-эндпоинты Финанс-Аудит (продукт №2): субъекты анализа фактической отчётности.

Все операции ограничены текущей организацией (изоляция арендатора, как проекты):
субъект из чужой организации недоступен (404). Права переиспуют проектные (кто ведёт
проекты — ведёт и субъекты аудита).
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from audit_core import AuditSubjectModel, Elimination, analyze, consolidate_subjects
from audit_core.opinion import build_opinion

from .. import crud
from ..audit_docgen import DOCX_MIME, build_audit_docx
from ..database import get_db
from ..db_models import AuditGroup, AuditSubject
from ..deps import require_permission
from ..rbac import Perm
from ..schemas import (
    AuditAnalysisOut,
    AuditConsolidateRequest,
    AuditConsolidateResponse,
    AuditEliminationIn,
    AuditGroupCreate,
    AuditGroupModel,
    AuditGroupOut,
    AuditGroupSummary,
    AuditGroupUpdate,
    AuditSubjectCreate,
    AuditSubjectOut,
    AuditSubjectSummary,
    AuditSubjectUpdate,
    audit_analysis_response,
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


@router.post("/subjects/{subject_id}/analyze", response_model=AuditAnalysisOut)
def analyze_subject(subject_id: str,
                    org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                    db: Session = Depends(get_db)) -> AuditAnalysisOut:
    """Проанализировать отчётность субъекта: аналитическая форма, тренды, коэффициенты."""
    subject = _require(db, org_id, subject_id)
    result = analyze(crud.load_audit_model(subject))
    return audit_analysis_response(result, build_opinion(result))


def _consolidate(members: list[tuple[str, AuditSubjectModel]], name: str,
                 elimination: AuditEliminationIn | None,
                 missing: list[str]) -> AuditConsolidateResponse:
    """Собрать свод и проанализировать его как единое предприятие.

    ``missing`` — участники сохранённой группы, которых больше нет: свод считается по
    оставшимся, а о выбывших сообщается **первой** оговоркой (состав изменился — числа
    свода уже не те, что были при сохранении).
    """
    warnings: list[str] = []
    if missing:
        warnings.append("Состав группы изменился: участники не найдены (удалены) — "
                        f"{', '.join(missing)}. Свод посчитан по оставшимся.")

    if members:
        elim = (Elimination(receivables=list(elimination.receivables),
                            revenue=list(elimination.revenue))
                if elimination is not None else None)
        consolidation = consolidate_subjects(members, name=name, elimination=elim)
        warnings += consolidation.warnings
        model, periods_used = consolidation.model, consolidation.periods_used
    else:
        # Все участники удалены: свод пуст. Пустой анализ честнее, чем ошибка, — группа
        # существует, в ней просто некого сводить, и это сказано в оговорке выше.
        warnings.append("В группе не осталось ни одного участника — сводить нечего.")
        model, periods_used = AuditSubjectModel(name=name), []

    result = analyze(model)
    analysis = audit_analysis_response(result, build_opinion(result))
    # Оговорки свода идут вперёд предупреждений самого анализа.
    analysis.warnings = warnings + list(analysis.warnings)
    return AuditConsolidateResponse(
        analysis=analysis,
        members=[nm for nm, _ in members],
        periods_used=periods_used,
        warnings=warnings,
        missing_members=missing,
    )


@router.post("/consolidate", response_model=AuditConsolidateResponse)
def consolidate(body: AuditConsolidateRequest,
                org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                db: Session = Depends(get_db)) -> AuditConsolidateResponse:
    """Свод отчётности группы субъектов и анализ группы как единого предприятия.

    Внутригрупповые обороты исключаются, только если переданы явно (``elimination``);
    иначе свод их не вычитает — это отражено в предупреждениях ответа.
    """
    members: list[tuple[str, AuditSubjectModel]] = []
    for sid in body.subject_ids:
        subject = _require(db, org_id, sid)
        members.append((subject.name, crud.load_audit_model(subject)))
    # Разовый свод падает на неизвестном субъекте (404) → выбывших участников не бывает.
    return _consolidate(members, body.name, body.elimination, missing=[])


@router.get("/subjects/{subject_id}/report.docx")
def download_report(subject_id: str,
                    org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                    db: Session = Depends(get_db)) -> Response:
    """Документ заключения по анализу (DOCX): заключение, отчёты, коэффициенты, диагностика."""
    subject = _require(db, org_id, subject_id)
    model = crud.load_audit_model(subject)
    result = analyze(model)
    content = build_audit_docx(result, build_opinion(result), subject_name=subject.name,
                               industry=model.industry, currency=model.currency)
    filename = quote(f"{subject.name or 'audit'}.docx")
    return Response(content=content, media_type=DOCX_MIME, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
    })


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: str,
                   org_id: str = Depends(require_permission(Perm.PROJECT_DELETE)),
                   db: Session = Depends(get_db)) -> None:
    """Удалить субъект анализа."""
    crud.delete_audit_subject(db, _require(db, org_id, subject_id))


# --- Сохранённые группы предприятий (v2) ---

def _resolve_members(db: Session, org_id: str, model: AuditGroupModel,
                     ) -> tuple[list[tuple[str, AuditSubjectModel]], list[str]]:
    """Разложить состав группы на живых участников и выбывших (субъект удалён).

    Живому участнику имя берётся из субъекта — переименование субъекта видно в своде.
    Выбывшего называем по имени на момент сохранения: иного следа от него не осталось.
    """
    alive: list[tuple[str, AuditSubjectModel]] = []
    missing: list[str] = []
    for member in model.members:
        subject = crud.get_audit_subject(db, org_id, member.subject_id)
        if subject is None:
            missing.append(member.name or member.subject_id)
        else:
            alive.append((subject.name, crud.load_audit_model(subject)))
    return alive, missing


def _group_out(db: Session, org_id: str, group: AuditGroup) -> AuditGroupOut:
    model = crud.load_audit_group_model(group)
    _, missing = _resolve_members(db, org_id, model)
    return AuditGroupOut(id=group.id, name=group.name, created_at=group.created_at,
                         updated_at=group.updated_at, n_members=len(model.members),
                         n_missing=len(missing), model=model)


def _require_group(db: Session, org_id: str, group_id: str) -> AuditGroup:
    group = crud.get_audit_group(db, org_id, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    return group


@router.post("/groups", response_model=AuditGroupOut, status_code=status.HTTP_201_CREATED)
def create_group(body: AuditGroupCreate,
                 org_id: str = Depends(require_permission(Perm.PROJECT_CREATE)),
                 db: Session = Depends(get_db)) -> AuditGroupOut:
    """Сохранить состав группы предприятий (участники + внутригрупповые обороты)."""
    return _group_out(db, org_id, crud.create_audit_group(db, org_id, body.name, body.model))


@router.get("/groups", response_model=list[AuditGroupSummary])
def list_groups(org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                db: Session = Depends(get_db)) -> list[AuditGroupSummary]:
    """Список сохранённых групп (с числом участников и числом выбывших)."""
    return [_group_out(db, org_id, g) for g in crud.list_audit_groups(db, org_id)]


@router.get("/groups/{group_id}", response_model=AuditGroupOut)
def get_group(group_id: str,
              org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
              db: Session = Depends(get_db)) -> AuditGroupOut:
    """Получить сохранённую группу с составом."""
    return _group_out(db, org_id, _require_group(db, org_id, group_id))


@router.put("/groups/{group_id}", response_model=AuditGroupOut)
def update_group(group_id: str, body: AuditGroupUpdate,
                 org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE)),
                 db: Session = Depends(get_db)) -> AuditGroupOut:
    """Обновить имя и/или состав сохранённой группы."""
    group = _require_group(db, org_id, group_id)
    return _group_out(db, org_id,
                      crud.update_audit_group(db, group, name=body.name, model=body.model))


@router.post("/groups/{group_id}/analyze", response_model=AuditConsolidateResponse)
def analyze_group(group_id: str,
                  org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE)),
                  db: Session = Depends(get_db)) -> AuditConsolidateResponse:
    """Свод сохранённой группы по **текущей** отчётности участников.

    Группа хранит состав, а не результат: числа всегда пересчитываются. Если участника
    удалили, свод считается по оставшимся, а выбывшие названы в оговорках ответа.
    """
    group = _require_group(db, org_id, group_id)
    model = crud.load_audit_group_model(group)
    members, missing = _resolve_members(db, org_id, model)
    return _consolidate(members, group.name, model.elimination, missing=missing)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: str,
                 org_id: str = Depends(require_permission(Perm.PROJECT_DELETE)),
                 db: Session = Depends(get_db)) -> None:
    """Удалить сохранённую группу (субъекты-участники не затрагиваются)."""
    crud.delete_audit_group(db, _require_group(db, org_id, group_id))
