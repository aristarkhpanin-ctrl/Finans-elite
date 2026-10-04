"""Ссылка для инвестора или банка (пакет L, L4).

План делают, чтобы показать тем, кто даёт деньги. Ссылка открывает **снимок** — версию
проекта — без входа и регистрации: показатели, отчёты, бизнес-план в DOCX с пометкой
«копия для …». Правила, и каждое держит тест:

* **снимок, а не живая модель**: правка проекта после отправки чужую копию не меняет;
  если с тех пор сменилась методика (версия движка), копия говорит об этом прямо;
* **срок обязателен** (по умолчанию 30 дней, не больше 90) — обрезка названа, а не
  молчалива; «бессрочная ссылка на финансовую модель» — это утечка с отсрочкой;
* **секрет показывается один раз**, хранится отпечаток (как у ключа API);
* **закрытие мгновенное и строку не удаляет**; отказы разные — «не найдена», «закрыта
  отправителем», «срок истёк», «проект или версия удалены» — и каждый своими словами;
* **каждое открытие — в журнал организации**: по какой ссылке и когда. Кто открыл —
  неизвестно (ссылку могли переслать), и это напечатано, а не угадано.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import crud
from .database import as_tenant
from .db_models import AuditLogEntry, Project, ProjectVersion, ShareLink
from .timefmt import day_utc

DEFAULT_DAYS = 30
MAX_DAYS = 90
#: Сколько живых ссылок на проект: ссылка — дверь наружу, и сотня забытых дверей уже не
#: контроль, а решето.
MAX_ACTIVE_PER_PROJECT = 20
TOKEN_PREFIX = "fs_"

OPEN = "share.open"


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def aware(moment: datetime) -> datetime:
    """SQLite отдаёт время без пояса (значения в нём — UTC); наружу оно уходит с поясом,
    иначе браузер принял бы его за местное."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def clamp_days(days: int | None) -> tuple[int, str]:
    """Срок ссылки и оговорка, если его пришлось обрезать."""
    wanted = days or DEFAULT_DAYS
    if wanted < 1:
        return 1, "Срок меньше дня не бывает — ссылка открыта на 1 день."
    if wanted > MAX_DAYS:
        return MAX_DAYS, (f"Ссылка открыта на {MAX_DAYS} дней вместо {wanted}: дольше "
                          "финансовую модель по ссылке не держат — пришлите новую, если нужно.")
    return wanted, ""


def state(link: ShareLink, now: datetime | None = None) -> str:
    """``active`` | ``revoked`` | ``expired``."""
    now = now or datetime.now(timezone.utc)
    if link.revoked_at is not None:
        return "revoked"
    if aware(link.expires_at) <= now:
        return "expired"
    return "active"


def refusal(kind: str, link: ShareLink | None = None) -> str:
    """Отказ посетителю — своими словами на каждый случай."""
    if kind == "revoked" and link is not None and link.revoked_at is not None:
        return (f"Ссылку закрыл отправитель {day_utc(link.revoked_at)}. Попросите "
                "прислать новую, если она ещё нужна.")
    if kind == "expired" and link is not None:
        return (f"Срок ссылки истёк {day_utc(link.expires_at)}. Попросите "
                "отправителя прислать новую.")
    if kind == "gone":
        return ("Ссылка больше не действует: отправитель удалил проект или версию, которую "
                "по ней открывали.")
    return "Ссылка не найдена — проверьте, что она скопирована целиком."


@dataclass
class Opened:
    link: ShareLink
    version: ProjectVersion
    project: Project
    org_name: str


def find(db: Session, token: str) -> ShareLink | None:
    """Ссылка по секрету — **без арендатора**: её предъявляет посторонний."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    return db.scalar(select(ShareLink).where(ShareLink.fingerprint == fingerprint(token)))


def open_shared(db: Session, token: str, *, what: str) -> Opened | tuple[int, str]:
    """Открыть снимок по ссылке и записать открытие в журнал организации.

    Возвращает либо открытое, либо пару «статус, причина» отказа. Запись в журнал —
    **внутри арендатора**: журнал под RLS, а организация известна только из найденной
    строки.
    """
    link = find(db, token)
    if link is None:
        return 404, refusal("missing")
    kind = state(link)
    if kind != "active":
        return 410, refusal(kind, link)
    with as_tenant(db, link.organization_id):
        version = db.get(ProjectVersion, link.version_id)
        project = db.get(Project, link.project_id)
        org = crud.get_organization(db, link.organization_id)
        if version is None or project is None or org is None:
            return 410, refusal("gone")
        visitor = SimpleNamespace(id=None, email=f"по ссылке «{link.label}»")
        # Действие — литералом: перечень подписей журнала (test_journal_labels) читает
        # вызовы по исходнику; совпадение с OPEN, по которому считаются открытия, держит тест.
        crud.log_action(db, link.organization_id, visitor, "share.open",
                        entity_type="share_link",
                        entity_id=link.id, entity_name=link.label, details=what)
        return Opened(link=link, version=version, project=project, org_name=org.name)


def opens(db: Session, org_id: str, link_ids: list[str]) -> dict[str, tuple[int, datetime | None]]:
    """Сколько раз открывали каждую ссылку и когда последний раз — **из журнала**, а не
    из счётчика: второй источник того же ответа однажды разошёлся бы с первым."""
    if not link_ids:
        return {}
    rows = db.execute(
        select(AuditLogEntry.entity_id, func.count(), func.max(AuditLogEntry.created_at))
        .where(AuditLogEntry.organization_id == org_id, AuditLogEntry.action == OPEN,
               AuditLogEntry.entity_id.in_(link_ids))
        .group_by(AuditLogEntry.entity_id)).all()
    return {entity_id: (int(count), last) for entity_id, count, last in rows}


def create(db: Session, *, project: Project, version: ProjectVersion, label: str,
           days: int, created_by: str, engine_version: str) -> tuple[ShareLink, str]:
    token = new_token()
    link = ShareLink(
        organization_id=project.organization_id, project_id=project.id,
        version_id=version.id, label=label, fingerprint=fingerprint(token),
        created_by=created_by, engine_version=engine_version,
        expires_at=datetime.now(timezone.utc) + timedelta(days=days))
    db.add(link)
    db.commit()
    db.refresh(link)
    return link, token


def active_count(db: Session, org_id: str, project_id: str) -> int:
    now = datetime.now(timezone.utc)
    links = db.execute(select(ShareLink).where(ShareLink.organization_id == org_id,
                                               ShareLink.project_id == project_id)).scalars()
    return sum(1 for link in links if state(link, now) == "active")


def list_for(db: Session, org_id: str, project_id: str) -> list[ShareLink]:
    return list(db.execute(
        select(ShareLink).where(ShareLink.organization_id == org_id,
                                ShareLink.project_id == project_id)
        .order_by(ShareLink.created_at.desc())).scalars())


def get(db: Session, org_id: str, project_id: str, link_id: str) -> ShareLink | None:
    return db.scalar(select(ShareLink).where(
        ShareLink.id == link_id, ShareLink.organization_id == org_id,
        ShareLink.project_id == project_id))


def revoke(db: Session, link: ShareLink, *, by: str) -> None:
    if link.revoked_at is None:
        link.revoked_at = datetime.now(timezone.utc)
        link.revoked_by = by
        db.commit()
