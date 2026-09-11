"""REST-эндпоинты Финанс-Аудит (продукт №2): субъекты анализа фактической отчётности.

Все операции ограничены текущей организацией (изоляция арендатора, как проекты):
субъект из чужой организации недоступен (404). Права переиспуют проектные (кто ведёт
проекты — ведёт и субъекты аудита).
"""
from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from audit_core import (
    AuditSubjectModel,
    Benchmark,
    Elimination,
    analyze,
    compare_subjects,
    consolidate_subjects,
    review_case,
)
from audit_core.opinion import build_opinion
from audit_core.samples import build_trading_subject

from .. import billing, crud, usage
from ..audit_docgen import DOCX_MIME, build_audit_docx
from ..database import get_db
from ..db_models import AuditGroup, AuditSubject, AuditSubjectVersion, User
from ..deps import current_user, require_permission
from ..rbac import Perm
from ..schemas import (
    AuditAnalysisOut,
    AuditCaseColumnOut,
    AuditCompareRequest,
    AuditCompareResponse,
    AuditCompareRowOut,
    AuditConsolidateRequest,
    AuditConsolidateResponse,
    AuditEliminationIn,
    AuditGroupCreate,
    AuditGroupModel,
    AuditGroupOut,
    AuditGroupSummary,
    AuditGroupUpdate,
    AuditMetricChangeOut,
    AuditRiskOut,
    AuditSubjectCreate,
    AuditSubjectOut,
    AuditSubjectSummary,
    AuditSubjectUpdate,
    AuditVersionDiffOut,
    AuditVersionOut,
    AuditVersionSummary,
    ModelChangeOut,
    VersionCreate,
    audit_analysis_response,
    audit_risk_response,
)
from ..versioning import diff_case_metrics, diff_models

#: У каждого маршрута названа **своя подписка**: продукты продаются порознь, и
#: просроченный «Аудит» не имеет отношения к оплаченному «Элит» (B2, режим чтения и
#: выгрузки). Без явного `product` маршрут спрашивал бы про подписку чужого продукта —
#: молча и в пользу нарушителя.
router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def _summary(s: AuditSubject) -> AuditSubjectSummary:
    m = crud.load_audit_model(s)
    # Светофор считается здесь же: карточка дела в списке показывает состояние цели,
    # и без него список — это просто имена. Анализ чистый и дешёвый (арифметика над
    # ≤48 периодами), отдельного хранения не заводим: хранился бы результат, который
    # расходится с отчётностью после первой же правки.
    result = analyze(m) if m.n else None
    return AuditSubjectSummary(
        id=s.id, name=s.name, created_at=s.created_at, updated_at=s.updated_at,
        n_periods=m.n, balanced=m.is_balanced(), industry=m.industry,
        light=result.diagnostics.light if result and result.diagnostics else None)


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
                   org_id: str = Depends(require_permission(Perm.PROJECT_CREATE, product="audit")),
                   actor: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> AuditSubjectOut:
    """Создать субъект анализа в текущей организации."""
    billing.ensure_case_quota(db, org_id)
    subject = crud.create_audit_subject(db, org_id, body.name, body.model)
    crud.log_action(db, org_id, actor, "case.create", entity_type="case",
                    entity_id=subject.id, entity_name=subject.name)
    usage.record(db, event="case.create", org_id=org_id, email=actor.email)
    return _out(subject)


@router.get("/subjects", response_model=list[AuditSubjectSummary])
def list_subjects(org_id: str = Depends(require_permission(Perm.PROJECT_READ, product="audit")),
                  db: Session = Depends(get_db)) -> list[AuditSubjectSummary]:
    """Список субъектов анализа организации (метаданные)."""
    return [_summary(s) for s in crud.list_audit_subjects(db, org_id)]


@router.get("/subjects/{subject_id}", response_model=AuditSubjectOut)
def get_subject(subject_id: str,
                org_id: str = Depends(require_permission(Perm.PROJECT_READ, product="audit")),
                db: Session = Depends(get_db)) -> AuditSubjectOut:
    """Получить субъект с моделью и сходимостью баланса по периодам."""
    return _out(_require(db, org_id, subject_id))


@router.put("/subjects/{subject_id}", response_model=AuditSubjectOut)
def update_subject(subject_id: str, body: AuditSubjectUpdate,
                   org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE, product="audit")),
                   actor: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> AuditSubjectOut:
    """Обновить имя и/или модель субъекта."""
    subject = _require(db, org_id, subject_id)
    updated = crud.update_audit_subject(db, subject, name=body.name, model=body.model)
    crud.log_action(db, org_id, actor, "case.update", entity_type="case",
                    entity_id=updated.id, entity_name=updated.name,
                    details="отчётность" if body.model is not None else "имя")
    return _out(updated)


#: Имя демо-дела. Пометка о вымышленности живёт **в имени**, а не рядом с ним: имя
#: путешествует с делом всюду — в список, в свод группы, в шапку DOCX-заключения. Флаг
#: в базе показывался бы только там, где его не забыли прочитать, и однажды демонстрация
#: ушла бы инвесткомитету как настоящая проверка.
DEMO_NAME = "Демо-дело: ООО «Торговый дом» (вымышленные данные)"


@router.post("/subjects/demo", response_model=AuditSubjectOut,
             status_code=status.HTTP_201_CREATED)
def create_demo_subject(org_id: str = Depends(require_permission(Perm.PROJECT_CREATE, product="audit")),
                        actor: User = Depends(current_user),
                        db: Session = Depends(get_db)) -> AuditSubjectOut:
    """Завести демо-дело из эталонного семпла («Экран 18»).

    Обычное дело, а не особый режим: его можно править, дублировать и удалить теми же
    кнопками. Так у нового пользователя сразу есть на чём увидеть работающий продукт —
    аналитическую форму, коэффициенты, диагностику и заключение, — и ему не нужно
    сперва вводить чужую отчётность, чтобы понять, что он покупает.
    """
    billing.ensure_case_quota(db, org_id)
    subject = crud.create_audit_subject(db, org_id, DEMO_NAME, build_trading_subject())
    crud.log_action(db, org_id, actor, "case.create", entity_type="case",
                    entity_id=subject.id, entity_name=subject.name, details="демо-дело")
    return _out(subject)


@router.post("/subjects/{subject_id}/duplicate", response_model=AuditSubjectOut,
             status_code=status.HTTP_201_CREATED)
def duplicate_subject(subject_id: str,
                      org_id: str = Depends(require_permission(Perm.PROJECT_CREATE, product="audit")),
                      actor: User = Depends(current_user),
                      db: Session = Depends(get_db)) -> AuditSubjectOut:
    """Дублировать дело: модель целиком, имя «{name} (копия)»."""
    subject = _require(db, org_id, subject_id)
    billing.ensure_case_quota(db, org_id)
    copy = crud.duplicate_audit_subject(db, subject, f"{subject.name} (копия)")
    crud.log_action(db, org_id, actor, "case.duplicate", entity_type="case",
                    entity_id=copy.id, entity_name=copy.name,
                    details=f"копия дела «{subject.name}»")
    return _out(copy)


def _benchmarks(db: Session, org_id: str) -> list[Benchmark]:
    """Ориентиры организации для разбора: они принадлежат ей, а не делу."""
    return [Benchmark(industry=b.industry, metric=b.metric, value=Decimal(b.value),
                      source=b.source,
                      updated_at=b.updated_at.date() if b.updated_at else None)
            for b in crud.list_benchmarks(db, org_id)]


@router.post("/subjects/{subject_id}/analyze", response_model=AuditAnalysisOut)
def analyze_subject(subject_id: str,
                    org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE, product="audit")),
                    db: Session = Depends(get_db)) -> AuditAnalysisOut:
    """Проанализировать отчётность субъекта: аналитическая форма, тренды, коэффициенты.

    **Без стохастики** (`deep=False`). Анализ дёргается при каждом открытии дела и после
    каждой правки модели, а Монте-Карло — единственный дорогой слой: на объявленных
    неопределённых допущениях разбор шёл 0,9 с при 2 000 прогонов и 8,7 с при 20 000
    вместо 6 мс, и платил за это тот, кто пользуется самой продвинутой функцией. Риски
    считаются там, где их показывают: `…/risk`, документ, выгрузка.
    """
    subject = _require(db, org_id, subject_id)
    # Конвейер один на экран и на документ (`audit_core.pipeline`): вторая копия
    # порядка слоёв однажды уже разошлась с первой и молчала о находках.
    r = review_case(crud.load_audit_model(subject), deep=False,
                    benchmarks=_benchmarks(db, org_id))
    # Разбор дела журнал не пишет (это чтение результата) — событие пишет: без него
    # «пользуются ли вторым продуктом» отвечать нечем.
    usage.record(db, event="case.analyze", org_id=org_id)
    return audit_analysis_response(r.result, r.opinion, r.issues, r.flags, r.earnings,
                                   r.obligations, r.procedures, r.summary, r.valuation,
                                   r.risk, r.plan_fact, r.benchmark, r.requisites)


@router.post("/subjects/{subject_id}/risk", response_model=AuditRiskOut)
def analyze_subject_risk(subject_id: str,
                         org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE, product="audit")),
                         db: Session = Depends(get_db)) -> AuditRiskOut:
    """Анализ рисков оценки: торнадо и Монте-Карло (SPEC, Прил. Р).

    Отдельный вызов, потому что это единственный дорогой слой: его просят, открывая
    вкладку рисков или скачивая документ, а не каждым открытием дела. Разбор идёт тем
    же конвейером — числа те же, что в остальных разделах.
    """
    subject = _require(db, org_id, subject_id)
    return audit_risk_response(review_case(crud.load_audit_model(subject)).risk)


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
                            revenue=list(elimination.revenue),
                            investments=list(elimination.investments),
                            unrealized_profit=list(elimination.unrealized_profit))
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


@router.post("/compare", response_model=AuditCompareResponse)
def compare(body: AuditCompareRequest,
            org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE, product="audit")),
            db: Session = Depends(get_db)) -> AuditCompareResponse:
    """Сравнить дела организации (SPEC, Приложение С).

    Сравнение разовое, как свод группы: хранится запрос, а не результат — числа всегда
    по текущей отчётности дел.
    """
    subjects: list[tuple[str, AuditSubjectModel]] = []
    for sid in body.subject_ids:
        subject = _require(db, org_id, sid)
        subjects.append((subject.id, crud.load_audit_model(subject)))
    comparison = compare_subjects(subjects)
    return AuditCompareResponse(
        cases=[AuditCaseColumnOut(
            subject_id=c.subject_id, name=c.name, industry=c.industry,
            currency=c.currency, reporting_standard=c.reporting_standard,
            last_period=c.last_period, n_periods=c.n_periods, verdict=c.verdict,
            base_code=c.base_code) for c in comparison.cases],
        rows=[AuditCompareRowOut(
            key=r.key, label=r.label, unit=r.unit, direction=r.direction,
            values=list(r.values), texts=list(r.texts), winner=r.winner, note=r.note)
            for r in comparison.rows],
        wins=list(comparison.wins), comparable=comparison.comparable,
        caveats=list(comparison.caveats), excluded=list(comparison.excluded),
        not_computed=list(comparison.not_computed),
    )


@router.post("/consolidate", response_model=AuditConsolidateResponse)
def consolidate(body: AuditConsolidateRequest,
                org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE, product="audit")),
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


# --- Версии дела: снимки модели проверки и анализ изменений ---

def _version_summary(v: AuditSubjectVersion) -> AuditVersionSummary:
    return AuditVersionSummary(
        id=v.id, label=v.label, created_at=v.created_at, verdict=v.verdict,
        risk_flags=v.risk_flags,
        equity_value=Decimal(v.equity_value) if v.equity_value else None)


def _version_out(v: AuditSubjectVersion) -> AuditVersionOut:
    return AuditVersionOut(
        **_version_summary(v).model_dump(),
        model=AuditSubjectModel.model_validate(v.model))


def _require_version(db: Session, org_id: str, subject_id: str, version_id: str):
    version = crud.get_audit_version(db, org_id, subject_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Версия не найдена")
    return version


def _case_summary(model: AuditSubjectModel) -> tuple[str | None, int | None, str | None]:
    """Сводка дела на момент снимка: вердикт, флаги риска, стоимость доли.

    Стохастика не нужна (`deep=False`): в сводку идёт то, что видно в шапке дела.
    Пустое дело вердикта не имеет — ``None`` вместо «ok», иначе снимок пустого дела
    читался бы в списке как «проверено, всё хорошо».
    """
    review = review_case(model, deep=False)
    if review.summary.state != "ready":
        return None, None, None
    equity = review.valuation.equity_value
    return (review.summary.verdict, review.summary.risk_flags,
            str(equity) if equity is not None else None)


@router.post("/subjects/{subject_id}/versions", response_model=AuditVersionSummary,
             status_code=status.HTTP_201_CREATED)
def create_version(subject_id: str, body: VersionCreate,
                   org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE, product="audit")),
                   actor: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> AuditVersionSummary:
    """Снимок текущей модели дела как именованная версия (со сводкой на этот момент)."""
    subject = _require(db, org_id, subject_id)
    if crud.count_audit_versions(db, subject_id) >= crud.MAX_VERSIONS_PER_SUBJECT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Достигнут лимит версий на дело ({crud.MAX_VERSIONS_PER_SUBJECT}). "
                   "Удалите ненужные версии.")
    verdict, risk_flags, equity = _case_summary(crud.load_audit_model(subject))
    label = body.label.strip() or f"Версия от {subject.updated_at:%d.%m.%Y %H:%M}"
    version = crud.create_audit_version(db, subject, label, verdict=verdict,
                                        risk_flags=risk_flags, equity_value=equity)
    crud.log_action(db, org_id, actor, "case.version", entity_type="case",
                    entity_id=subject.id, entity_name=subject.name, details=label)
    return _version_summary(version)


@router.get("/subjects/{subject_id}/versions", response_model=list[AuditVersionSummary])
def list_versions(subject_id: str,
                  org_id: str = Depends(require_permission(Perm.PROJECT_READ, product="audit")),
                  db: Session = Depends(get_db)) -> list[AuditVersionSummary]:
    """Версии дела (метаданные, новейшие сверху)."""
    _require(db, org_id, subject_id)
    return [_version_summary(v) for v in crud.list_audit_versions(db, org_id, subject_id)]


@router.get("/subjects/{subject_id}/versions/{version_id}", response_model=AuditVersionOut)
def get_version(subject_id: str, version_id: str,
                org_id: str = Depends(require_permission(Perm.PROJECT_READ, product="audit")),
                db: Session = Depends(get_db)) -> AuditVersionOut:
    """Версия с полной моделью снимка."""
    _require(db, org_id, subject_id)
    return _version_out(_require_version(db, org_id, subject_id, version_id))


@router.delete("/subjects/{subject_id}/versions/{version_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_version(subject_id: str, version_id: str,
                   org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE, product="audit")),
                   actor: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> None:
    """Удалить версию."""
    subject = _require(db, org_id, subject_id)
    version = _require_version(db, org_id, subject_id, version_id)
    label = version.label
    crud.delete_audit_version(db, version)
    crud.log_action(db, org_id, actor, "case.version_delete", entity_type="case",
                    entity_id=subject.id, entity_name=subject.name, details=label)


@router.get("/subjects/{subject_id}/versions/{version_id}/diff",
            response_model=AuditVersionDiffOut)
def diff_version(subject_id: str, version_id: str, against: str = "current",
                 org_id: str = Depends(require_permission(Perm.PROJECT_READ, product="audit")),
                 db: Session = Depends(get_db)) -> AuditVersionDiffOut:
    """Что изменилось от снимка к другой версии или к текущему состоянию дела.

    ``against`` — id другой версии либо ``current``. old = эта версия, new = сравниваемое
    состояние: диф отвечает на вопрос «что стало с делом с тех пор».
    """
    subject = _require(db, org_id, subject_id)
    base = _require_version(db, org_id, subject_id, version_id)
    against_model = (subject.model if against == "current"
                     else _require_version(db, org_id, subject_id, against).model)

    changes, truncated = diff_models(base.model, against_model)
    metric_changes: list[AuditMetricChangeOut] = []
    try:
        base_review = review_case(AuditSubjectModel.model_validate(base.model), deep=False)
        against_review = review_case(AuditSubjectModel.model_validate(against_model),
                                     deep=False)
        metric_changes = [
            AuditMetricChangeOut(key=c.key, label=c.label, old=c.old, new=c.new)
            for c in diff_case_metrics(base_review, against_review)
        ]
    except (ValidationError, ValueError):
        # Одна из моделей не разбирается — остаётся диф модели: он не требует расчёта.
        metric_changes = []

    return AuditVersionDiffOut(
        base_id=version_id, against=against,
        model_changes=[ModelChangeOut(path=c.path, kind=c.kind, old=c.old, new=c.new)
                       for c in changes],
        model_changes_truncated=truncated,
        metric_changes=metric_changes,
    )


@router.post("/subjects/{subject_id}/versions/{version_id}/restore",
             response_model=AuditSubjectOut)
def restore_version(subject_id: str, version_id: str,
                    org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE, product="audit")),
                    actor: User = Depends(current_user),
                    db: Session = Depends(get_db)) -> AuditSubjectOut:
    """Вернуть модель версии в рабочее дело."""
    subject = _require(db, org_id, subject_id)
    version = _require_version(db, org_id, subject_id, version_id)
    updated = crud.update_audit_subject(
        db, subject, model=AuditSubjectModel.model_validate(version.model))
    crud.log_action(db, org_id, actor, "case.version_restore", entity_type="case",
                    entity_id=subject.id, entity_name=subject.name, details=version.label)
    return _out(updated)


@router.get("/subjects/{subject_id}/report.docx")
def download_report(subject_id: str,
                    org_id: str = Depends(require_permission(Perm.PROJECT_READ, product="audit")),
                    actor: User = Depends(current_user),
                    db: Session = Depends(get_db)) -> Response:
    """Документ заключения по анализу (DOCX): заключение, отчёты, коэффициенты, диагностика."""
    subject = _require(db, org_id, subject_id)
    # Тот же разбор, что отдаётся на экран: документ обязан рассказывать то же самое,
    # включая находки, оценку, риски и списки «что не посчитано».
    content = build_audit_docx(review_case(crud.load_audit_model(subject),
                                           benchmarks=_benchmarks(db, org_id)),
                               subject_name=subject.name)
    # Выгрузка документа — вынос данных за пределы системы, и для 152-ФЗ это событие
    # важнее половины правок: именно так отчётность цели покидает контур.
    crud.log_action(db, org_id, actor, "case.export", entity_type="case",
                    entity_id=subject.id, entity_name=subject.name, details="DOCX-заключение")
    filename = quote(f"{subject.name or 'audit'}.docx")
    usage.record(db, event="case.report", org_id=org_id, email=actor.email)
    return Response(content=content, media_type=DOCX_MIME, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
    })


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: str,
                   org_id: str = Depends(require_permission(Perm.PROJECT_DELETE, product="audit")),
                   actor: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> None:
    """Удалить субъект анализа."""
    subject = _require(db, org_id, subject_id)
    # Имя запоминается до удаления: после него журнал уже не смог бы назвать,
    # что именно исчезло, — а это главное, что от записи об удалении и нужно.
    name = subject.name
    crud.delete_audit_subject(db, subject)
    crud.log_action(db, org_id, actor, "case.delete", entity_type="case",
                    entity_id=subject_id, entity_name=name)


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
                 org_id: str = Depends(require_permission(Perm.PROJECT_CREATE, product="audit")),
                 actor: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> AuditGroupOut:
    """Сохранить состав группы предприятий (участники + внутригрупповые обороты)."""
    group = crud.create_audit_group(db, org_id, body.name, body.model)
    crud.log_action(db, org_id, actor, "group.create", entity_type="group",
                    entity_id=group.id, entity_name=group.name)
    return _group_out(db, org_id, group)


@router.get("/groups", response_model=list[AuditGroupSummary])
def list_groups(org_id: str = Depends(require_permission(Perm.PROJECT_READ, product="audit")),
                db: Session = Depends(get_db)) -> list[AuditGroupSummary]:
    """Список сохранённых групп (с числом участников и числом выбывших)."""
    return [_group_out(db, org_id, g) for g in crud.list_audit_groups(db, org_id)]


@router.get("/groups/{group_id}", response_model=AuditGroupOut)
def get_group(group_id: str,
              org_id: str = Depends(require_permission(Perm.PROJECT_READ, product="audit")),
              db: Session = Depends(get_db)) -> AuditGroupOut:
    """Получить сохранённую группу с составом."""
    return _group_out(db, org_id, _require_group(db, org_id, group_id))


@router.put("/groups/{group_id}", response_model=AuditGroupOut)
def update_group(group_id: str, body: AuditGroupUpdate,
                 org_id: str = Depends(require_permission(Perm.PROJECT_UPDATE, product="audit")),
                 actor: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> AuditGroupOut:
    """Обновить имя и/или состав сохранённой группы."""
    group = _require_group(db, org_id, group_id)
    updated = crud.update_audit_group(db, group, name=body.name, model=body.model)
    crud.log_action(db, org_id, actor, "group.update", entity_type="group",
                    entity_id=updated.id, entity_name=updated.name,
                    details="состав" if body.model is not None else "имя")
    return _group_out(db, org_id, updated)


@router.post("/groups/{group_id}/analyze", response_model=AuditConsolidateResponse)
def analyze_group(group_id: str,
                  org_id: str = Depends(require_permission(Perm.PROJECT_CALCULATE, product="audit")),
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
                 org_id: str = Depends(require_permission(Perm.PROJECT_DELETE, product="audit")),
                 actor: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> None:
    """Удалить сохранённую группу (субъекты-участники не затрагиваются)."""
    group = _require_group(db, org_id, group_id)
    name = group.name
    crud.delete_audit_group(db, group)
    crud.log_action(db, org_id, actor, "group.delete", entity_type="group",
                    entity_id=group_id, entity_name=name)
