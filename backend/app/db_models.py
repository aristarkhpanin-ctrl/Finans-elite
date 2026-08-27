"""ORM-модели (SQLAlchemy 2.0).

6.1 — проекты; 6.2 — мультиарендность (организации, пользователи, членство; проекты
привязаны к организации). Изоляция данных — по ``organization_id`` (ARCHITECTURE §4).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# JSONB на PostgreSQL, JSON на остальных (SQLite).
JSONType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    """Арендатор (компания-клиент)."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    """Пользователь. ``hashed_password`` отсутствует у приглашённых (без входа) до активации."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Membership(Base):
    """Членство пользователя в организации с ролью (роли — RBAC, 6.4)."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Subscription(Base):
    """Подписка организации на тариф — **своя на каждый продукт платформы**.

    Продукты продаются порознь, поэтому уникальна пара «организация + продукт», а не
    одна организация: общая подписка означала бы, что цена «Аудита» меняется вместе с
    ценой «Элит» и наоборот.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("organization_id", "product", name="uq_org_product"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: "business" («Финанс-Элит») | "audit" («Финанс-Аудит»).
    product: Mapped[str] = mapped_column(String(16), default="business",
                                         server_default="business", nullable=False)
    plan_code: Mapped[str] = mapped_column(String(32), default="free")
    status: Mapped[str] = mapped_column(String(32), default="active")  # active/trialing/past_due/canceled
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Payment(Base):
    """Платёж за смену тарифа (для интеграции с провайдером, 6.5b)."""

    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), default="yookassa")
    provider_payment_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_rub: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/succeeded/canceled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Holding(Base):
    """Холдинг: группа связанных проектов организации (PIC Holding, 9.3)."""

    __tablename__ = "holdings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Сводка последней консолидации (B3): NPV и ставка группы (строками, как model),
    # момент расчёта. NULL — консолидации ещё не было.
    last_consolidation_npv: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_consolidation_rate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_consolidation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class HoldingMember(Base):
    """Участник холдинга: проект с ролью (parent — головная компания, subsidiary — дочерняя)."""

    __tablename__ = "holding_members"
    __table_args__ = (UniqueConstraint("holding_id", "project_id", name="uq_holding_project"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    holding_id: Mapped[str] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), default="subsidiary")  # parent | subsidiary


class Project(Base):
    """Проект финансовой модели (замена файла ``.pex``), принадлежит организации."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Сериализованная ProjectModel (mode="json": Decimal → строка, даты → ISO).
    model: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    # Сводка последнего успешного расчёта (B1). Decimal хранится строкой —
    # как и в model (точность без плавающей запятой). NULL — расчёта не было.
    last_npv: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_irr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_pb_months: Mapped[int | None] = mapped_column(nullable=True)
    last_engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_calculated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Финализация плана (Ф10, гейт ревью): "draft" | "finalized". Финализация возможна
    # только после ревью; risk-находки требуют явного подтверждения (acknowledge).
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft",
                                        nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # SHA-256 канонического JSON модели на момент финализации — детект «дрейфа» (модель
    # изменили после финализации). Снимок ревью — для показа, чем план был подтверждён.
    finalized_model_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finalized_review: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class ProjectVersion(Base):
    """Именованный снимок модели проекта (пакет №8, gap 4.4): версии + анализ изменений.

    Хранит полную модель на момент снимка + сводку расчёта (NPV/IRR/движок). Диф двух
    версий (или версии с текущей моделью) считается на лету. Изоляция — по
    ``organization_id`` (RLS + фильтр CRUD), каскадное удаление с проектом.
    """

    __tablename__ = "project_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    model: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Сводка расчёта на момент снимка (строки — точность без плавающей запятой); NULL — не считалось.
    npv: Mapped[str | None] = mapped_column(String(64), nullable=True)
    irr_annual: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


class AuditSubject(Base):
    """Субъект анализа финансового состояния (Финанс-Аудит, продукт №2).

    Принадлежит организации; хранит модель субъекта (реквизиты, периоды, фактическая
    отчётность) как JSON — по образцу ``Project.model``. Изоляция арендатора — RLS +
    фильтр CRUD по ``organization_id`` (как projects/holdings).
    """

    __tablename__ = "audit_subjects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Сериализованная AuditSubjectModel (mode="json": Decimal → строка).
    model: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AuditGroup(Base):
    """Сохранённая группа предприятий (Финанс-Аудит, v2): состав свода + исключения.

    Хранит **состав**, а не результат: свод пересчитывается по текущей отчётности
    участников при каждом анализе. Участник хранится как ``subject_id`` + имя на момент
    сохранения — имя нужно только чтобы назвать удалённого участника (у живых имя берётся
    из самого субъекта). Изоляция арендатора — RLS + фильтр CRUD по ``organization_id``.
    """

    __tablename__ = "audit_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Сериализованная AuditGroupModel (участники + внутригрупповые обороты).
    model: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AuditLogEntry(Base):
    """Журнал действий: кто, что и когда сделал в организации (152-ФЗ, ARCHITECTURE §4).

    Запись делает тот же запрос, что выполнил действие, сразу после его успеха. Строгой
    атомарности с самим действием нет — CRUD фиксирует транзакцию сам, — и это записано
    здесь честно, а не выдано за гарантию: обещанная в комментарии неразрывность, которой
    в коде нет, опаснее отсутствующей, потому что на неё сошлются при разборе инцидента.

    ``actor_email`` продублирован текстом рядом с ``user_id`` намеренно. Участника можно
    удалить из организации, и тогда ссылка перестанет что-либо называть; журнал же обязан
    отвечать на вопрос «кто это сделал» и через год после увольнения. Тот же приём, что у
    имени участника в сохранённой группе, — «надгробие».

    Запись не редактируется и не удаляется: в API нет ни PUT, ни DELETE. Срок хранения
    (5 лет по ARCHITECTURE §4) — политика эксплуатации, а не логика приложения; чистка
    журнала кодом означала бы, что приложение умеет стирать собственные следы.
    """

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Кто. Ссылка обнуляется при удалении пользователя, ``actor_email`` остаётся.
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    #: Что: машинный код действия («project.create», «member.role_change», …).
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Над чем: тип и идентификатор объекта плюс его имя на момент действия.
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    #: Подробности, зависящие от действия (старая и новая роль, код тарифа и т. п.).
    details: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class AnalysisJob(Base):
    """Фоновая задача анализа (Celery): реестр владения для изоляции арендатора.

    Статус и результат хранит бэкенд Celery; здесь — привязка ``job_id`` к организации
    (чтобы чужой арендатор не мог опросить задачу) и тип/время для аудита.
    """

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # = id задачи Celery
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # "monte_carlo"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
