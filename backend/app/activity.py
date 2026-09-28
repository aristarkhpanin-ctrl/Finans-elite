"""Активность организации: кто работает и что живо (NEXT-STEPS.md, E1).

Вопрос, который владелец организации задаёт вслух: «кто у меня работает и за что я
плачу». Ответ собирается из того, что платформа **уже** знает — отметки присутствия
участников (A3), журнала действий (A2) и дат последнего расчёта проектов и дел. Новых
таблиц и новых счётчиков не заводится: сводка, собранная из уже существующего, не может
разойтись с тем, что показывают другие экраны.

**Три границы едут вместе с числами**, иначе сводка обещает больше, чем знает:

* отметка присутствия ведётся **с точностью до часа** и **не с первого дня платформы** —
  пустое «заходил» значит «неизвестно», а не «никогда»;
* журнал **не пишет чтение** — «действий 0» значит «ничего не менял», а не «не работал»;
* расчётов платформа **не считает** — известна только дата последнего, и «не считали с
  апреля» это не то же самое, что «не открывали».

Чистые функции над CRUD: ни FastAPI, ни схем ответа. Читает — и ничего не меняет.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import crud
from .db_models import AuditLogEntry, AuditSubject, Comment, Project

#: За какой период считаем действия участника. Месяц — окно, в котором ещё помнят, что
#: происходило, и по которому уже видно, работает человек или числится.
WINDOW = timedelta(days=30)

#: Когда сущность считается спящей. Квартал: проект, который не открывали три месяца,
#: обычно закончен или заброшен — и то и другое повод про него вспомнить.
STALE = timedelta(days=90)


@dataclass
class MemberActivity:
    """Участник: когда заходил и сколько всего наменял за окно."""

    user_id: str
    email: str
    full_name: str
    role: str
    blocked: bool = False
    #: ``None`` — **неизвестно**, а не «никогда»: отметка ведётся не с первого дня.
    last_seen_at: datetime | None = None
    #: Записей журнала за окно. Ноль = «ничего не менял»: чтение журнал не пишет.
    actions: int = 0


@dataclass
class EntityActivity:
    """Проект или дело: когда правили и когда считали."""

    id: str
    name: str
    kind: str                       # "project" | "case"
    updated_at: datetime | None = None
    #: Дата последнего расчёта; числа расчётов у платформы нет.
    last_calculated_at: datetime | None = None
    #: Не трогали дольше :data:`STALE`.
    stale: bool = False
    #: Открытых обсуждений (D3) — вопросов, на которые ещё не ответили.
    open_comments: int = 0


@dataclass
class ActivityReport:
    """Сводка организации. ``notes`` — границы, без которых числа обещают лишнее."""

    members: list[MemberActivity] = field(default_factory=list)
    entities: list[EntityActivity] = field(default_factory=list)
    #: Сколько дней в окне — чтобы «действий 12» читалось «за месяц», а не вообще.
    window_days: int = int(WINDOW.days)
    stale_days: int = int(STALE.days)
    notes: list[str] = field(default_factory=list)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _actions_per_member(db: Session, org_id: str, since: datetime) -> dict[str, int]:
    """Сколько записей журнала оставил каждый участник за окно.

    Считается по **почте актора**, а не по ``user_id``: журнал обязан отвечать «кто это
    сделал» и после удаления учётной записи, и почта там остаётся «надгробием».
    """
    rows = db.execute(
        select(AuditLogEntry.actor_email, func.count())
        .where(AuditLogEntry.organization_id == org_id,
               AuditLogEntry.created_at >= since,
               AuditLogEntry.actor_email != "")
        .group_by(AuditLogEntry.actor_email)
    ).all()
    return {email: int(count) for email, count in rows}


def _open_comments(db: Session, org_id: str) -> dict[tuple[str, str], int]:
    """Незакрытые обсуждения по сущностям: (тип, id) → сколько."""
    rows = db.execute(
        select(Comment.subject_type, Comment.subject_id, func.count())
        .where(Comment.organization_id == org_id,
               Comment.resolved_at.is_(None), Comment.deleted_at.is_(None))
        .group_by(Comment.subject_type, Comment.subject_id)
    ).all()
    return {(kind, sid): int(count) for kind, sid, count in rows}


def build_activity(db: Session, org_id: str,
                   now: datetime | None = None) -> ActivityReport:
    """Собрать сводку активности организации.

    Зовётся **внутри арендатора** (маршрут входит в него зависимостью): проекты, дела,
    журнал и обсуждения — под RLS.
    """
    now = now or datetime.now(timezone.utc)
    since = now - WINDOW
    actions = _actions_per_member(db, org_id, since)
    comments = _open_comments(db, org_id)

    members = [
        MemberActivity(
            user_id=user.id, email=user.email, full_name=user.full_name,
            role=membership.role, blocked=membership.blocked_at is not None,
            last_seen_at=_aware(membership.last_seen_at),
            actions=actions.get(user.email, 0),
        )
        for membership, user in crud.list_members(db, org_id)
    ]

    entities: list[EntityActivity] = []
    for project in db.execute(select(Project).where(
            Project.organization_id == org_id)).scalars():
        touched = _aware(project.updated_at)
        entities.append(EntityActivity(
            id=project.id, name=project.name, kind="project",
            updated_at=touched, last_calculated_at=_aware(project.last_calculated_at),
            stale=touched is not None and now - touched >= STALE,
            open_comments=comments.get(("project", project.id), 0)))
    for case in db.execute(select(AuditSubject).where(
            AuditSubject.organization_id == org_id)).scalars():
        touched = _aware(case.updated_at)
        entities.append(EntityActivity(
            id=case.id, name=case.name, kind="case", updated_at=touched,
            stale=touched is not None and now - touched >= STALE,
            open_comments=comments.get(("case", case.id), 0)))
    entities.sort(key=lambda e: (e.updated_at is None, e.updated_at), reverse=True)

    return ActivityReport(members=members, entities=entities, notes=_notes(members))


def _notes(members: list[MemberActivity]) -> list[str]:
    """Границы сводки — словами и рядом с числами.

    Сводка без них читается как отчёт о людях: «заходил — пусто» превращается в «не
    работает», а «действий 0» — в «бездельничает». Ни того, ни другого платформа не
    знает.
    """
    notes = [
        "«Действий» — это записи журнала: созданное, изменённое, удалённое и выгруженное. "
        "Просмотры журнал не пишет, поэтому ноль означает «ничего не менял», а не «не "
        "заходил».",
        "Расчётов платформа не считает — известна только дата последнего. «Не считали с "
        "апреля» и «не открывали с апреля» это разные утверждения.",
    ]
    if any(m.last_seen_at is None for m in members):
        notes.append(
            "У части участников нет отметки присутствия: она ведётся не с первого дня "
            "платформы и обновляется не чаще раза в час. Пусто — это «неизвестно», а не "
            "«никогда не заходил».")
    return notes
